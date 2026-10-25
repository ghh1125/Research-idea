"""Question-directed reading must deliver exact, bounded source locations."""
import unittest

from research_idea.controller import make_evidence, select_excerpt
from research_idea.focused_reading import select_focused_excerpt


class FocusedReadingTests(unittest.TestCase):
    def assert_exact_spans(self, text, result, limit):
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result['excerpt']), limit)
        spans = result['spans']
        previous_end = -1
        for span in spans:
            start, end = span['start'], span['end']
            self.assertGreater(start, previous_end)
            self.assertLess(start, end)
            self.assertLessEqual(end, len(text))
            previous_end = end
        self.assertEqual(result['excerpt'], '\n\n'.join(
            f"[SOURCE SPAN {span['start']}:{span['end']}]\n{text[span['start']:span['end']]}" for span in spans))

    def test_deep_acquisition_and_reliability_passage_is_available(self):
        quote = ('We obtain executable labels by running each program twice, compare the returned values, '
                 'and retain timeout and disagreement records for reliability calibration.')
        text = '1 Introduction\n' + 'General background. ' * 1500
        text += '\n2 Method\n' + 'General method description. ' * 1500
        text += '\n\n' + quote + '\n\n' + 'Other details. ' * 1500
        text += '\n3 Experiments\n' + 'Aggregate measurements. ' * 1000
        self.assertNotIn(quote, select_excerpt(text, 1200))
        result = select_focused_excerpt(text, 1200, ['executable labels', 'reliability calibration'],
                                        'How are labels obtained and disagreements retained?')
        self.assert_exact_spans(text, result, 1200)
        self.assertIn(quote, result['excerpt'])
        self.assertEqual(result['matched_terms'], ['executable labels', 'reliability calibration'])
        self.assertIn('does not establish scientific relevance', result['selection_note'])

    def test_budget_counts_markers_and_preserves_unicode_and_line_endings(self):
        text = ('原文保持不变。\r\nLabel acquisition uses measured outputs.\r\n' * 500)
        for limit in (0, 1, 20, 50, 100, 256, 900, 2400):
            with self.subTest(limit=limit):
                result = select_focused_excerpt(text, limit, ['label acquisition'])
                if result is not None:
                    self.assert_exact_spans(text, result, limit)
                    self.assertIn('acquisition', result['excerpt'].casefold())

    def test_question_ranks_body_matches_and_references_do_not_crowd_them_out(self):
        intro = 'Label acquisition is mentioned as background.\n\n' + 'Background text. ' * 300
        detail = 'Label acquisition records failed execution and calibrates uncertainty against adjudicated examples.'
        text = intro + '\n\n' + detail + '\n\n' + 'Unrelated discussion. ' * 300
        text += '\nReferences\n' + ('Label acquisition execution uncertainty calibration, prior work citation.\n' * 100)
        result = select_focused_excerpt(text, 400, ['label acquisition'],
                                        'How does execution uncertainty use adjudicated examples?')
        self.assert_exact_spans(text, result, 400)
        self.assertIn(detail, result['excerpt'])
        self.assertNotIn('prior work citation', result['excerpt'])

    def test_appendix_after_references_remains_readable(self):
        text = 'Main text.\nReferences\n[1] An executable label construction paper.\n'
        text += '\nAppendix A Label construction\nExecutable label construction records exception types.'
        result = select_focused_excerpt(text, 300, ['executable label construction'])
        self.assert_exact_spans(text, result, 300)
        self.assertIn('records exception types', result['excerpt'])
        self.assertNotIn('[1]', result['excerpt'])

    def test_windows_reference_heading_is_recognized_without_changing_text(self):
        text = 'Main text without the requested term.\r\n\r\n## 8 References\r\n[1] Label acquisition.'
        self.assertIsNone(select_focused_excerpt(text, 300, ['label acquisition']))

    def test_overlapping_hits_and_duplicate_terms_do_not_duplicate_source(self):
        text = ('Context. ' * 50 + '\n\nLabel acquisition and label verification share executable supervision.\n\n'
                + 'Further detail. ' * 100)
        result = select_focused_excerpt(text, 1400,
                                        ['label acquisition', 'LABEL acquisition', 'label verification', 'executable supervision'])
        self.assert_exact_spans(text, result, 1400)
        self.assertEqual(result['excerpt'].count('Label acquisition and label verification'), 1)
        self.assertEqual(len(result['matched_terms']), 3)

    def test_invalid_terms_no_body_hits_and_question_only_hits_use_fallback(self):
        text = 'Execution provides labels.\nReferences\nLabel acquisition in earlier work.'
        for terms in ([], None, ['the', 'and'], ['中文关键词'], ['missing phrase'], ['label acquisition']):
            with self.subTest(terms=terms):
                self.assertIsNone(select_focused_excerpt(text, 500, terms, 'Execution provides labels'))

    def test_terms_are_literal_and_support_wrapped_phrases(self):
        text = 'Calibration uses label\nacquisition from controlled execution. Another phrase is a+b.'
        result = select_focused_excerpt(text, 300, ['label acquisition', 'a+b', '.*'])
        self.assert_exact_spans(text, result, 300)
        self.assertEqual(result['matched_terms'], ['label acquisition'])

    def test_evidence_uses_the_read_duplicate_occurrence(self):
        quote = 'The labels are obtained by executing the original program.'
        text = quote + '\n\n' + 'Intervening discussion. ' * 200
        text += '\n\nAcquisition details: ' + quote + ' Failures retain their exception type for calibration.\n\n'
        text += 'Additional text. ' * 100
        result = select_focused_excerpt(text, 350, ['acquisition details'], 'How are failures calibrated?')
        observation = dict(statement='Execution supplies the label.', quote=quote, kind='author_claim',
                           conditions='Programs that can execute', source_section='Acquisition details')
        paper = dict(id='source', text=text, content_kind='full_text')
        records = make_evidence(paper, [observation], result['excerpt'], source_spans=result['spans'])
        self.assertEqual(records[0]['start'], text.rindex(quote))
        self.assertEqual(text[records[0]['start']:records[0]['end']], quote)

    def test_quote_cannot_cross_separate_source_spans(self):
        first = 'Execution supplies the labels.'
        second = 'Calibration measures their disagreement.'
        # The full quote exists elsewhere in unread source text. Whole-source
        # matching would incorrectly accept a stitched pair of supplied spans.
        text = first + ' ' + second + '\n\n' + 'Unread intervening information. ' * 100
        text += '\n\n' + first + '\n\n' + 'More unread material. ' * 100 + '\n\n' + second
        start = text.rindex(first)
        spans = [{'start': start, 'end': start + len(first)}, {'start': text.rindex(second), 'end': len(text)}]
        # A stitched quote can look fluent and even appear in an unmarked
        # concatenation. It must still be located inside one real source span.
        excerpt = first + '\n\n' + second
        observation = dict(statement='Execution and calibration form one claim.', quote=first + ' ' + second,
                           kind='author_claim', conditions='Synthetic source', source_section='Method')
        with self.assertRaises(ValueError):
            make_evidence(dict(id='source', text=text, content_kind='full_text'), [observation], excerpt,
                          source_spans=spans)


if __name__ == '__main__':
    unittest.main()
