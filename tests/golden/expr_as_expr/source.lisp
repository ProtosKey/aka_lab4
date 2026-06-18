; Demonstrates that every form in this dialect is an expression.
; The result of any form can be used as an argument, assigned with setq,
; or passed directly to a built-in.
;
; Expected output: "1 3 9 Y\n"

; 1. (setq x e) is an expression — returns the assigned value.
;    Here the result of setq feeds directly into putc.
(putc (+ 48 (setq x 1)))       ; x <- 1, prints chr(49) = '1'
(putc 32)                       ; space

; 2. (if c t f) is an expression — result can be assigned with setq.
(setq r (if (= x 1) 3 0))      ; r <- 3
(putc (+ 48 r))                 ; prints chr(51) = '3'
(putc 32)                       ; space

; 3. (loop c b1 ... bk) is an expression — returns the last body value
;    of the final iteration (or 0 if the body never ran).
(setq i 0)
(setq r (loop (< i 3)
  (setq i (+ i 1))
  (* i i)))                     ; iterations: 1, 4, 9 — r <- 9
(putc (+ 48 r))                 ; prints chr(57) = '9'
(putc 32)                       ; space

; 4. (if c t f) as a direct argument — no intermediate variable needed.
(putc (if (= r 9) 89 78))      ; if r=9: 'Y' (89), else 'N' (78)
(putc 10)                       ; newline
