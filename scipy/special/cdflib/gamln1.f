      DOUBLE PRECISION FUNCTION gamln1(a)
C-----------------------------------------------------------------------
C     EVALUATION OF LN(GAMMA(1 + A)) FOR -0.2 .LE. A .LE. 1.25
C-----------------------------------------------------------------------
C     .. Scalar Arguments ..
      DOUBLE PRECISION a
C     ..
C     .. Local Scalars ..
      DOUBLE PRECISION p0,p1,p2,p3,p4,p5,p6,q1,q2,q3,q4,q5,q6,r0,r1,r2,
     +                 r3,r4,r5,s1,s2,s3,s4,s5,w,x
C     ..
C     .. Data statements ..
C----------------------
      DATA p0/.577215664901533D+00/,p1/.844203922187225D+00/,
     +     p2/-.168860593646662D+00/,p3/-.780427615533591D+00/,
     +     p4/-.402055799310489D+00/,p5/-.673562214325671D-01/,
     +     p6/-.271935708322958D-02/
      DATA q1/.288743195473681D+01/,q2/.312755088914843D+01/,
     +     q3/.156875193295039D+01/,q4/.361951990101499D+00/,
     +     q5/.325038868253937D-01/,q6/.667465618796164D-03/
      DATA r0/.422784335098467D+00/,r1/.848044614534529D+00/,
     +     r2/.565221050691933D+00/,r3/.156513060486551D+00/,
     +     r4/.170502484022650D-01/,r5/.497958207639485D-03/
      DATA s1/.124313399877507D+01/,s2/.548042109832463D+00/,
     +     s3/.101552187439830D+00/,s4/.713309612391000D-02/,
     +     s5/.116165475989616D-03/
C     ..
C     .. Executable Statements ..
C----------------------
      IF (a.GE.0.6D0) GO TO 10
      w = ((((((p6*a+p5)*a+p4)*a+p3)*a+p2)*a+p1)*a+p0)/
     +    ((((((q6*a+q5)*a+q4)*a+q3)*a+q2)*a+q1)*a+1.0D0)
      gamln1 = -a*w
      RETURN
C
   10 x = (a-0.5D0) - 0.5D0
      w = (((((r5*x+r4)*x+r3)*x+r2)*x+r1)*x+r0)/
     +    (((((s5*x+s4)*x+s3)*x+s2)*x+s1)*x+1.0D0)
      gamln1 = x*w
      RETURN

      END