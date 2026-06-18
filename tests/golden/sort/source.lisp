; Sort a list of positive integers using bubble sort.
;
; Input format (cstr-inspired, 0-terminated):
;   <n1>\n <n2>\n ... <nk>\n 0\n
;
; Output: sorted integers, one per line.

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

; Array lives at byte address 2048 (well past the globals section).
(setq arr 2048)
(setq cnt 0)

; Read numbers into array until sentinel 0.
(setq num (read-int))
(loop num
  (store (+ arr (* cnt 4)) num)
  (setq cnt (+ cnt 1))
  (setq num (read-int)))

; Bubble sort (O(n^2), ascending).
(setq pass 0)
(loop (< pass cnt)
  (setq j 0)
  (loop (< j (- cnt 1))
    (setq ea (load (+ arr (* j 4))))
    (setq eb (load (+ arr (* (+ j 1) 4))))
    (if (> ea eb)
      (progn
        (store (+ arr (* j 4)) eb)
        (store (+ arr (* (+ j 1) 4)) ea))
      0)
    (setq j (+ j 1)))
  (setq pass (+ pass 1)))

; Print sorted array.
(setq si 0)
(loop (< si cnt)
  (print-int (load (+ arr (* si 4))))
  (putc 10)
  (setq si (+ si 1)))
