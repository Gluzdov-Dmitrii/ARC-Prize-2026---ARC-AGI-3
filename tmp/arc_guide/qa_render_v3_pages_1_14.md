# Render v3 page review

Reviewed the original page PNG files 1 through 14 on 2026-09-22. The document
was rebuilt immediately before rendering, incorporating the median and
percentage-point explanations. Word export and canonical PNG rendering both
completed with exit code 0; no cleanup warning from this run.

Required corrections reported to the root agent:

1. Page 1 has a blue horizontal line below the Title. Remove the inherited
   paragraph border per the document skill.
2. Pages 1 and 9 repeat a diagram whose Plan subtitle reaches the box edge.
   Reduce its font slightly or wrap its label.
3. Page 13 begins its independent numbered instructions at 5, continuing the
   list on page 3. Restart at 1, then continue 1 through 9 on page 13.
4. Page 10 says the box moved after contact from the right to the right,
   contradicting the preceding illustrative diagram. Suggested wording:
   “Ящик сдвинулся вправо после толчка слева”.
5. Minor typography: page 6 splits 70 000 across lines in the prize table.
   Use nonbreaking spaces in grouped monetary amounts.

All reviewed pages have readable text and equations, visible table borders,
and no clipping, missing glyphs, or text overlap. The planned page divisions
remain intact on pages 1 through 14.

Word cleanup status: the failed render v2 instance PID 26528 was recovered
through its native COM window, validated by exact document path and read-only
status, and closed successfully. The older render v1 PID 6104 still existed
at the last check but exposed no recoverable document window. No unrelated
Word processes or documents were modified. The successful v3 cleanup used
parameterless Close()/Quit(), avoiding Windows PowerShell optional-argument
COM binding failures.
