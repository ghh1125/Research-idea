"""Bounded reading selection is source sampling, not full-paper coverage."""
import re
import unittest

from research_idea.controller import make_evidence, select_excerpt


class ReadingSpanTests(unittest.TestCase):
    def assert_original_spans(self, source, excerpt, limit):
        markers = list(re.finditer(r"\[SOURCE SPAN (\d+):(\d+)\]\n", excerpt))
        self.assertTrue(markers)
        self.assertLessEqual(len(excerpt), limit)
        for index, marker in enumerate(markers):
            start, end = map(int, marker.groups())
            span_end = markers[index + 1].start() - 2 if index + 1 < len(markers) else len(excerpt)
            self.assertEqual(excerpt[marker.end():span_end], source[start:end])
        return [(int(m[1]), int(m[2])) for m in markers]

    def test_many_early_method_sections_do_not_crowd_out_late_families(self):
        source = "1 Introduction\nINTRODUCTION_SENTINEL\n" + "intro filler " * 500
        source += "\n2 Methods\nMETHOD_SENTINEL\n" + "method filler " * 500
        for index in range(1, 16):
            source += f"\n2.{index} Method variant\n" + "early method detail " * 250
        for heading, sentinel in [
            ("3 Experimental Setup", "EXPERIMENT_SENTINEL"),
            ("4 Main Results", "RESULT_SENTINEL"),
            ("5 Limitations and Discussion", "LIMITATION_SENTINEL"),
            ("Appendix A Additional analysis", "APPENDIX_SENTINEL"),
        ]:
            source += f"\n{heading}\n{sentinel}\n" + "later content " * 500
        excerpt = select_excerpt(source, 2400)
        for sentinel in ["INTRODUCTION", "METHOD", "EXPERIMENT", "RESULT", "LIMITATION", "APPENDIX"]:
            self.assertIn(sentinel + "_SENTINEL", excerpt)
        self.assert_original_spans(source, excerpt, 2400)
        self.assertNotEqual(excerpt, source)

    def test_numbered_chinese_and_markdown_headings(self):
        source = "引言\nINTRODUCTION_SENTINEL\n" + "背景材料。" * 700
        for heading, sentinel in [
            ("## 第三章 方法", "METHOD_SENTINEL"),
            ("四、实验设置", "EXPERIMENT_SENTINEL"),
            ("5.2 实验结果", "RESULT_SENTINEL"),
            ("六、讨论与局限", "LIMITATION_SENTINEL"),
            ("附录 A 补充材料", "APPENDIX_SENTINEL"),
        ]:
            source += f"\n{heading}\n{sentinel}\n" + "段落内容。" * 700
        excerpt = select_excerpt(source, 1800)
        for sentinel in ["INTRODUCTION", "METHOD", "EXPERIMENT", "RESULT", "LIMITATION", "APPENDIX"]:
            self.assertIn(sentinel + "_SENTINEL", excerpt)
        self.assert_original_spans(source, excerpt, 1800)

    def test_without_headings_samples_beginning_middle_and_actual_end(self):
        source = "beginning " * 2000 + "middle " * 2000 + "ending " * 2000
        excerpt = select_excerpt(source, 1200)
        self.assertIn("beginning beginning", excerpt)
        self.assertIn("middle middle", excerpt)
        self.assertIn("ending ending", excerpt)
        spans = self.assert_original_spans(source, excerpt, 1200)
        self.assertEqual(spans[0][0], 0)
        self.assertTrue(any(start <= len(source) // 2 < end for start, end in spans))
        self.assertEqual(spans[-1][1], len(source))

    def test_short_text_is_unchanged(self):
        source = "1 Methods\nA short supplied source.\n2 Results\nA reported observation."
        self.assertEqual(select_excerpt(source, len(source)), source)
        self.assertEqual(select_excerpt(source, len(source) + 50), source)

    def test_sampled_result_retains_original_quote_offsets_and_partial_status(self):
        quote = "Performance decreases under the reported shifted evaluation conditions."
        source = "1 Introduction\n" + "context " * 1000
        source += "\n2 Methods\n" + "details " * 1000
        source += "\n3 Results\n" + quote + "\n" + "measurements " * 1000
        excerpt = select_excerpt(source, 1600)
        paper = {"id": "synthetic-paper", "text": source, "content_kind": "full_text"}
        observation = {
            "statement": "A conditional decrease is reported.", "quote": quote,
            "kind": "reported_result", "conditions": "shifted evaluation",
            "source_section": "Results",
        }
        evidence = make_evidence(paper, [observation], excerpt)[0]
        self.assertEqual(evidence["start"], source.index(quote))
        self.assertEqual(evidence["reading_coverage"], "partial")
        self.assertEqual(evidence["verification"], "quote_matched_only")
        with self.assertRaisesRegex(ValueError, "supplied source"):
            make_evidence(paper, [{**observation, "quote": "Performance improves across all reported evaluation conditions."}], excerpt)

    def test_small_budget_remains_bounded(self):
        source = "Introduction\n" + "material " * 1000
        for limit in [0, 1, 20, 80, 200]:
            with self.subTest(limit=limit):
                self.assertLessEqual(len(select_excerpt(source, limit)), limit)


if __name__ == "__main__":
    unittest.main()
