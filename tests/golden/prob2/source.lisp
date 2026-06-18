; Euler problem 6 — difference between the square of the sum
; and the sum of squares of the first N natural numbers.
;
; Input:  N (positive integer, newline-terminated)
; Output: (sum(1..N))^2 - sum(i^2 for i in 1..N)

(defun div10 (n)
  (setq q 0)
  (loop (>= n 10) (setq n (- n 10)) (setq q (+ q 1)))
  q)

(defun mod10 (n)
  (loop (>= n 10) (setq n (- n 10)))
  n)

(defun print-int (n)
  (if (< n 10)
      (putc (+ n 48))
      (progn
        (print-int (div10 n))
        (putc (+ (mod10 n) 48)))))

(defun read-int ()
  (setq acc 0)
  (setq c (getc))
  (loop (* (- c 10) c)
    (setq acc (+ (* acc 10) (- c 48)))
    (setq c (getc)))
  acc)

(defun sum (n)
  (setq s 0)
  (setq i 1)
  (loop (<= i n)
    (setq s (+ s i))
    (setq i (+ i 1)))
  s)

(defun sum-sq (n)
  (setq s 0)
  (setq i 1)
  (loop (<= i n)
    (setq s (+ s (* i i)))
    (setq i (+ i 1)))
  s)

(defun square (x) (* x x))

(setq n (read-int))
(print-int (- (square (sum n)) (sum-sq n)))
(putc 10)
