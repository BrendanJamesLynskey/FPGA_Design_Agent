import Gray.Spec
namespace Gray

/-- Brief 136, scenario 5: the statement a reviewer who rejects `gray_sample` ("a sample may also be taken mid-glitch") would want.
    A glitching sample is not "the old code or the new code": each BIT of the sampled bus may independently read as its old or its new value
    (the first flop of each bit of the synchroniser resolves on its own). For every width and every count: if every bit of the sampled value
    is the corresponding bit of the old code or of the new code, the decoded value is the old count or the new count. -/
theorem gray_sample_bitwise {n : Nat} (hn : 0 < n) (b g : BitVec n)
    (h : ∀ j : Nat, j < n → g.getLsbD j = (bin2gray b).getLsbD j ∨ g.getLsbD j = (bin2gray (b + 1)).getLsbD j) :
    gray2bin g = b ∨ gray2bin g = b + 1 := by
  obtain ⟨i, hi⟩ := gray_step hn b
  apply gray_sample hn b g
  have hdiff : ∀ j : Nat, (hj : j < n) → j ≠ i.val → (bin2gray b).getLsbD j = (bin2gray (b + 1)).getLsbD j := by
    intro j hj hne
    refine Classical.byContradiction (fun hc => ?_)
    have := (hi ⟨j, hj⟩).mp hc
    exact hne (congrArg Fin.val this)
  by_cases hgi : g.getLsbD i.val = (bin2gray b).getLsbD i.val
  · left
    apply bv_ext
    intro j hj
    by_cases hji : j = i.val
    · rw [hji]; exact hgi
    · rcases h j hj with h1 | h2
      · exact h1
      · rw [h2]; exact (hdiff j hj hji).symm
  · right
    apply bv_ext
    intro j hj
    by_cases hji : j = i.val
    · rw [hji]
      rcases h i.val i.isLt with h1 | h2
      · exact absurd h1 hgi
      · exact h2
    · rcases h j hj with h1 | h2
      · rw [h1]; exact hdiff j hj hji
      · exact h2

/-- The reason the statement needs the one-step condition: a sample whose bits come from codes TWO steps apart (a bit skew of a whole source clock
    or more) can decode outside the old-to-new range. Width 3, count 3 (gray 010) and count 5 (gray 111): the mixed value 011 decodes to 2. -/
example : gray2bin (0b011#3) = 2#3 ∧ (0b011#3 ≠ bin2gray 3#3) ∧ (0b011#3 ≠ bin2gray 4#3) ∧ (0b011#3 ≠ bin2gray 5#3) := by decide

end Gray
