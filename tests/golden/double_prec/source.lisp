; 64-bit arithmetic on a 32-bit machine.
;
; Represents a 64-bit integer as two 32-bit signed words (high, low).
; Demonstrates addition with carry propagation.
;
; Test case: (0, 0xFFFFFFFF) + (0, 1) = (1, 0)
;   0xFFFFFFFF == -1 in 32-bit signed == 4294967295 unsigned
;   Expected 64-bit sum: 2^32 = 4294967296
;   Represented as (high=1, low=0)
;
; Carry detection using signed comparisons:
;   carry = 1 iff unsigned addition of low words wraps around 2^32
;   = (both operands have bit-31 set)
;     OR (exactly one operand has bit-31 set AND result is non-negative)

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

; ── 64-bit addition ──────────────────────────────────────────────────────────

(setq a-hi 0)
(setq a-lo -1)    ; 0xFFFFFFFF — low word of a

(setq b-hi 0)
(setq b-lo 1)     ; 1           — low word of b

; Low word (may wrap in 32 bits)
(setq r-lo (+ a-lo b-lo))

; Sign bits of operands and result
(setq al-neg (< a-lo 0))
(setq bl-neg (< b-lo 0))
(setq rl-neg (< r-lo 0))

; c1: both operands negative (unsigned carry always occurs)
(setq c1 (* al-neg bl-neg))
; c2: exactly one operand negative AND result is non-negative
(setq c2 (* (= (+ al-neg bl-neg) 1) (- 1 rl-neg)))
(setq carry (if (+ c1 c2) 1 0))

; High word (add carries)
(setq r-hi (+ (+ a-hi b-hi) carry))

; Print: "<r-hi> <r-lo>\n"
(print-int r-hi)
(putc 32)
(print-int r-lo)
(putc 10)
