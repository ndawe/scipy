import numpy,scipy,scipy.sparse
from numpy import sqrt,ravel,diff,zeros,zeros_like,inner,concatenate,asarray
from scipy.sparse import csr_matrix,coo_matrix

from relaxation import gauss_seidel
from multilevel import multilevel_solver
from coarsen import sa_constant_interpolation
#from utils import infinity_norm
from utils import approximate_spectral_radius

def fit_candidate(I,x):
    """
    For each aggregate in I (i.e. each column of I) compute vector R and 
    sparse matrix Q (having the sparsity of I) such that the following holds:

        Q*R = x     and   Q^T*Q = I

    In otherwords, find a prolongator Q with orthonormal columns so that
    x is represented exactly on the coarser level by R.
    """
    x = asarray(x)
    Q = csr_matrix((x.copy(),I.indices,I.indptr),dims=I.shape,check=False)
    R = sqrt(ravel(csr_matrix((x*x,I.indices,I.indptr),dims=I.shape,check=False).sum(axis=0)))  #column 2-norms  

    Q.data *= (1.0/R)[Q.indices]  #normalize columns of Q
   
    #print "norm(R)",scipy.linalg.norm(R)
    #print "min(R),max(R)",min(R),max(R)
    #print "infinity_norm(Q.T*Q - I) ",infinity_norm((Q.T.tocsr() * Q - scipy.sparse.spidentity(Q.shape[1])))
    #print "norm(Q*R - x)",scipy.linalg.norm(Q*R - x)
    #print "norm(x - Q*Q.Tx)",scipy.linalg.norm(x - Q*(Q.T*x))
    return Q,R




##def orthonormalize_candidate(I,x,basis):
##    Px = csr_matrix((x,I.indices,I.indptr),dims=I.shape,check=False) 
##    Rs = []
##    #othogonalize columns of Px against other candidates 
##    for b in basis:
##        Pb = csr_matrix((b,I.indices,I.indptr),dims=I.shape,check=False)
##        R  = ravel(csr_matrix((Pb.data*Px.data,I.indices,I.indptr),dims=I.shape,check=False).sum(axis=0)) # columnwise projection of Px on Pb
##        Px.data -= R[I.indices] * Pb.data   #subtract component in b direction
##        Rs.append(R)
##
##    #filter columns here, set unused cols to 0, add to mask
##    
##    #normalize columns of Px
##    R = ravel(csr_matrix((x**x,I.indices,I.indptr),dims=I.shape,check=False).sum(axis=0))
##    Px.data *= (1.0/R)[I.indices]
##    Rs.append(R.reshape(-1,1))
##    return Rs

def hstack_csr(A,B):
    #OPTIMIZE THIS
    assert(A.shape[0] == B.shape[0])
    A = A.tocoo()
    B = B.tocoo()
    I = concatenate((A.row,B.row))
    J = concatenate((A.col,B.col+A.shape[1]))
    V = concatenate((A.data,B.data))
    return coo_matrix((V,(I,J)),dims=(A.shape[0],A.shape[1]+B.shape[1])).tocsr()


def vstack_csr(A,B):
    #OPTIMIZE THIS
    assert(A.shape[1] == B.shape[1])
    A = A.tocoo()
    B = B.tocoo()
    I = concatenate((A.row,B.row+A.shape[0]))
    J = concatenate((A.col,B.col))
    V = concatenate((A.data,B.data))
    return coo_matrix((V,(I,J)),dims=(A.shape[0]+B.shape[0],A.shape[1])).tocsr()
    


def orthonormalize_prolongator(P_l,x_l,W_l,W_m):
    """
     
    """
    X = csr_matrix((x_l,W_l.indices,W_l.indptr),dims=W_l.shape,check=False)  #candidate prolongator (assumes every value from x is used)
    
    R = (P_l.T.tocsr() * X)  # R has at most 1 nz per row
    X = X - P_l*R            # othogonalize X against P_l
    
    #DROP REDUNDANT COLUMNS FROM P (AND R?) HERE (NULL OUT R ACCORDINGLY?)    
    #REMOVE CORRESPONDING COLUMNS FROM W_l AND ROWS FROM A_m ALSO
    W_l_new = W_l
    W_m_new = W_m

    #normalize surviving columns of X
    col_norms = ravel(sqrt(csr_matrix((X.data*X.data,X.indices,X.indptr),dims=X.shape,check=False).sum(axis=0)))
    print "zero cols",sum(col_norms == 0)
    print "small cols",sum(col_norms < 1e-8)
    Xcopy = X.copy()
    X.data *= (1.0/col_norms)[X.indices]

    P_l_new = hstack_csr(P_l,X)


    #check orthonormality
    print "norm(P.T*P - I) ",scipy.linalg.norm((P_l_new.T * P_l_new - scipy.sparse.spidentity(P_l_new.shape[1])).data)
    #assert(scipy.linalg.norm((P_l_new.T * P_l_new - scipy.sparse.spidentity(P_l_new.shape[1])).data)<1e-8)
    
    x_m = zeros(P_l_new.shape[1],dtype=x_l.dtype)
    x_m[:P_l.shape[1]][diff(R.indptr).astype('bool')] = R.data
    x_m[P_l.shape[1]:] = col_norms

    print "||x_l - P_l*x_m||",scipy.linalg.norm(P_l_new* x_m - x_l) #see if x_l is represented exactly

    return P_l_new,x_m,W_l,W_m


def smoothed_prolongator(P,A):
    #just use Richardson for now
    #omega = 4.0/(3.0*approximate_spectral_radius(A))
    #return P - omega*(A*P)
    #return P  #TEST
    
    D = diag_sparse(A)
    D_inv_A = diag_sparse(1.0/D)*A
    omega = 4.0/(3.0*approximate_spectral_radius(D_inv_A))
    print "spectral radius",approximate_spectral_radius(D_inv_A)
    D_inv_A *= omega
    return P - D_inv_A*P
 


def sa_hierarchy(A,Ws,x):
    """
    Construct multilevel hierarchy using Smoothed Aggregation
        Inputs:
          A  - matrix
          Is - list of constant prolongators
          x  - "candidate" basis function to be approximated
        Ouputs:
          (As,Is,Ps) - tuple of lists
                  - As - [A, Ps[0].T*A*Ps[0], Ps[1].T*A*Ps[1], ... ]
                  - Is - smoothed prolongators 
                  - Ps - tentative prolongators
    """
    As = [A]
    Is = []
    Ps = []

    for W in Ws:
        #P,x = fit_candidate(W,x)
        P,x = fit_candidates(W,x)
        I   = smoothed_prolongator(P,A)  
        A   = I.T.tocsr() * A * I
        As.append(A)
        Ps.append(P)
        Is.append(I)
    return As,Is,Ps
         
def make_bridge(I,N):
    tail = I.indptr[-1].repeat(N - I.shape[0])
    ptr = concatenate((I.indptr,tail))
    return csr_matrix((I.data,I.indices,ptr),dims=(N,I.shape[1]),check=False)

class adaptive_sa_solver:
    def __init__(self,A,options=None,max_levels=10,max_coarse=100,max_candidates=1,mu=5,epsilon=0.1):
        self.A = A

        self.Rs = [] 
        
        #if self.A.shape[0] <= self.opts['coarse: max size']:
        #    raise ValueError,'small matrices not handled yet'
        
        x,AggOps = self.__initialization_stage(A,max_levels=max_levels,max_coarse=max_coarse,mu=mu,epsilon=epsilon) #first candidate
        
        Ws = AggOps

        self.candidates = [x]

        #create SA using x here
        As,Is,Ps = sa_hierarchy(A,Ws,self.candidates)

        for i in range(max_candidates - 1):
            x = self.__develop_candidate(A,As,Is,Ps,Ws,AggOps,mu=mu)    
            
            self.candidates.append(x)

            #if i == 0:
            #    x = arange(50).repeat(50).astype(float)
            #elif i == 1:
            #    x = arange(50).repeat(50).astype(float)
            #    x = numpy.ravel(transpose(x.reshape((50,50))))
           
            #As,Is,Ps,Ws = self.__augment_cycle(A,As,Ps,Ws,AggOps,x)             
            As,Is,Ps = sa_hierarchy(A,AggOps,self.candidates)
   
            #random.seed(0)
            #solver = multilevel_solver(As,Is)
            #x = solver.solve(zeros(A.shape[0]), x0=rand(A.shape[0]), tol=1e-12, maxiter=30)
            #self.candidates.append(x)

        self.Ps = Ps 
        self.solver = multilevel_solver(As,Is)
        self.AggOps = AggOps
                


    def __develop_candidate(self,A,As,Is,Ps,Ws,AggOps,mu):
        #scipy.random.seed(0)  #TEST
        x = scipy.rand(A.shape[0])
        b = zeros_like(x)

        solver = multilevel_solver(As,Is)

        x = solver.solve(b, x0=x, tol=1e-10, maxiter=mu)
    
        #TEST FOR CONVERGENCE HERE
 
        A_l,P_l,W_l,x_l = As[0],Ps[0],Ws[0],x
        
        temp_Is = []
        for i in range(len(As) - 2):
            P_l_new, x_m, W_l_new, W_m_new = orthonormalize_prolongator(P_l, x_l, W_l, AggOps[i+1])    
 
            I_l_new = smoothed_prolongator(P_l_new,A_l)
            A_m_new = I_l_new.T.tocsr() * A_l * I_l_new
            bridge = make_bridge(Is[i+1],A_m_new.shape[0]) 
 
            temp_solver = multilevel_solver( [A_m_new] + As[i+2:], [bridge] + Is[i+2:] )
 
            for n in range(mu):
                x_m = temp_solver.solve(zeros_like(x_m), x0=x_m, tol=1e-8, maxiter=1)
 
            temp_Is.append(I_l_new)
 
            W_l = vstack_csr(Ws[i+1],W_m_new)  #prepare for next iteration
            A_l = A_m_new
            x_l = x_m
            P_l = make_bridge(Ps[i+1],A_m_new.shape[0])
 
        x = x_l
        for I in reversed(temp_Is):
            x = I*x
        
        return x
           

    def __augment_cycle(self,A,As,Ps,Ws,AggOps,x):
        #make a new cycle using the new candidate
        A_l,P_l,W_l,x_l = As[0],Ps[0],AggOps[0],x            
        
        new_As,new_Is,new_Ps,new_Ws = [A],[],[],[AggOps[0]]

        for i in range(len(As) - 2):
            P_l_new, x_m, W_l_new, W_m_new = orthonormalize_prolongator(P_l, x_l, W_l, AggOps[i+1])

            I_l_new = smoothed_prolongator(P_l_new,A_l)
            A_m_new = I_l_new.T.tocsr() * A_l * I_l_new
            W_m_new = vstack_csr(Ws[i+1],W_m_new)

            new_As.append(A_m_new)
            new_Ws.append(W_m_new)
            new_Is.append(I_l_new)
            new_Ps.append(P_l_new)

            #prepare for next iteration
            W_l = W_m_new 
            A_l = A_m_new
            x_l = x_m
            P_l = make_bridge(Ps[i+1],A_m_new.shape[0]) 
        
        P_l_new, x_m, W_l_new, W_m_new = orthonormalize_prolongator(P_l, x_l, W_l, csr_matrix((P_l.shape[1],1)))
        I_l_new = smoothed_prolongator(P_l_new,A_l)
        A_m_new = I_l_new.T.tocsr() * A_l * I_l_new

        new_As.append(A_m_new)
        new_Is.append(I_l_new)
        new_Ps.append(P_l_new)

        return new_As,new_Is,new_Ps,new_Ws


    def __initialization_stage(self,A,max_levels,max_coarse,mu,epsilon):
        AggOps = []
        Is     = []

        # aSA parameters 
        # mu      - number of test relaxation iterations
        # epsilon - minimum acceptable relaxation convergence factor 
        
        #scipy.random.seed(0) #TEST

        #step 1
        A_l = A
        x   = scipy.rand(A_l.shape[0])
        skip_f_to_i = False
        
        #step 2
        b = zeros_like(x)
        gauss_seidel(A_l,x,b,iterations=mu,sweep='symmetric')
        #step 3
        #test convergence rate here 
      
        As = [A]

        while len(AggOps) + 1 < max_levels  and A_l.shape[0] > max_coarse:
            #W_l   = sa_constant_interpolation(A_l,epsilon=0.08*0.5**(len(AggOps)-1))           #step 4b  #TEST
            W_l   = sa_constant_interpolation(A_l,epsilon=0)              #step 4b
            P_l,x = fit_candidate(W_l,x)                                  #step 4c  
            I_l   = smoothed_prolongator(P_l,A_l)                         #step 4d
            A_l   = I_l.T.tocsr() * A_l * I_l                             #step 4e
            
            AggOps.append(W_l)
            Is.append(I_l)
            As.append(A_l)

            if A_l.shape <= max_coarse:  break

            if not skip_f_to_i:
                print "."
                x_hat = x.copy()                                                   #step 4g
                gauss_seidel(A_l,x,zeros_like(x),iterations=mu,sweep='symmetric')  #step 4h
                x_A_x = inner(x,A_l*x) 
                if (x_A_x/inner(x_hat,A_l*x_hat))**(1.0/mu) < epsilon:             #step 4i
                    print "sufficient convergence, skipping"
                    skip_f_to_i = True
                    if x_A_x == 0:       
                        x = x_hat  #need to restore x
        
        #update fine-level candidate
        for A_l,I in reversed(zip(As[1:],Is)):
            gauss_seidel(A_l,x,zeros_like(x),iterations=mu,sweep='symmetric')         #TEST
            x = I * x
        
        gauss_seidel(A,x,b,iterations=mu)         #TEST
    
        return x,AggOps  #first candidate,aggregation




from scipy import *
from utils import diag_sparse
from multilevel import poisson_problem1D,poisson_problem2D
A = poisson_problem2D(50)
#A = io.mmread("tests/sample_data/laplacian_41_3dcube.mtx").tocsr()
#A = io.mmread("laplacian_40_3dcube.mtx").tocsr()
#A = io.mmread("/home/nathan/Desktop/9pt/9pt-100x100.mtx").tocsr()
#A = io.mmread("/home/nathan/Desktop/BasisShift_W_EnergyMin_Luke/9pt-5x5.mtx").tocsr()

#A = A*A
#D = diag_sparse(1.0/sqrt(10**(12*rand(A.shape[0])-6))).tocsr()
#A = D * A * D
#A = io.mmread("nos2.mtx").tocsr()
asa = adaptive_sa_solver(A,max_candidates=1)
#x = arange(A.shape[0]).astype('d') + 1
scipy.random.seed(0)  #TEST
x = rand(A.shape[0])
b = zeros_like(x)


print "solving"
#x_sol,residuals = asa.solver.solve(b,x,tol=1e-8,maxiter=30,return_residuals=True)
if True:
    x_sol,residuals = asa.solver.solve(b,x0=x,maxiter=10,tol=1e-12,return_residuals=True)
else:
    residuals = []
    def add_resid(x):
        residuals.append(linalg.norm(b - A*x))
    A.psolve = asa.solver.psolve
    x_sol = linalg.cg(A,b,x0=x,maxiter=20,tol=1e-100,callback=add_resid)[0]
residuals = array(residuals)/residuals[0]
print "residuals ",residuals
print "mean convergence factor",(residuals[-1]/residuals[0])**(1.0/len(residuals))
print "last convergence factor",residuals[-1]/residuals[-2]

print
print asa.solver

print "constant Rayleigh quotient",dot(ones(A.shape[0]),A*ones(A.shape[0]))/float(A.shape[0])

for c in asa.candidates:
    print "candidate Rayleigh quotient",dot(c,A*c)/dot(c,c)



##W = asa.AggOps[0]*asa.AggOps[1]
##pcolor((W * rand(W.shape[1])).reshape((200,200)))

def plot2d(x):
    from pylab import pcolor
    pcolor(x.reshape(sqrt(len(x)),sqrt(len(x))))
    