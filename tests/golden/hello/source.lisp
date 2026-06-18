(defun print-str (p)
  (setq c (load-byte p))
  (loop c
    (putc c)
    (setq p (+ p 1))
    (setq c (load-byte p))))

(print-str "Hello, World!\n")
