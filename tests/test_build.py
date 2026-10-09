#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

BASE=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',BASE/'scripts/build_site.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        self.renderer=builder.Markdown(self.root,'docs/labs/00.md',{'docs/labs/00.md':'module/L00','docs/SAFETY.md':'document/docs/SAFETY.md'})
    def tearDown(self):self.tmp.cleanup()
    def test_escape_html_scripts_and_dangerous_urls(self):
        rendered=self.renderer.render('<script>alert(1)</script>\n\n[bad](javascript:alert) [good](https://st.com)')
        self.assertNotIn('<script>',rendered);self.assertNotIn('href="javascript:',rendered);self.assertIn('&lt;script&gt;',rendered);self.assertIn('https://st.com',rendered)
    def test_code_is_literal_even_with_markdown_and_script_tags(self):
        rendered=self.renderer.render('```c\nif (x < 2) { puts("</script>"); }\n[link](https://x.example)\n```')
        self.assertIn('&lt;/script&gt;',rendered);self.assertNotIn('<a href=',rendered);self.assertIn('copy-code',rendered)
    def test_local_routes_headings_and_code_links(self):
        rendered=self.renderer.render('# Заголовок\n## Проверка\n[Безопасность](../SAFETY.md) [`foo`](#проверка)\n## Проверка')
        self.assertIn('id="article-проверка"',rendered);self.assertIn('id="article-проверка-1"',rendered)
        self.assertIn('#document/docs/SAFETY.md',rendered);self.assertIn('<code>foo</code>',rendered)
        self.assertIn('#section/module/L00/',rendered)
    def test_nested_brackets_in_link_label(self):
        self.assertIn('>uart_console.[ch]</a>',self.renderer.inline('[uart_console.[ch]](../../examples/uart.c)'))
    def test_nested_lists_and_table(self):
        rendered=self.renderer.render('- one\n  - sub one\n  - sub two\n- two\n\n| A | B |\n| --- | --- |\n| x | `y` |')
        self.assertEqual(rendered.count('<ul>'),2);self.assertIn('<table>',rendered);self.assertIn('<th scope="col">A</th>',rendered)
    def test_raw_control_characters_cannot_forge_token(self):
        rendered=self.renderer.inline('text\x000\x00')
        self.assertEqual(rendered,'text0')
    def test_external_images_never_fetch_at_runtime(self):
        rendered=self.renderer.render('![board](https://example.com/board.png)')
        self.assertNotIn('<img',rendered);self.assertIn('внешнее изображение',rendered)
    def test_traversal_links_and_protocol_relative_urls_rejected(self):
        self.assertEqual(self.renderer.local('../../../secret'),(None,''))
        self.assertEqual(self.renderer.local('//example.org/x'),(None,''))
    def test_inline_backticks_keep_markdown_literal(self):
        rendered=self.renderer.inline('`**plain** [link](https://example.com)`')
        self.assertEqual(rendered,'<code>**plain** [link](https://example.com)</code>')
    def test_schema_validation_and_missing_files_are_fatal(self):
        schema={'schema_version':1,'id':'test','review_offsets_days':[1,3,7,21],'modules':[{'id':'L00','track':'core','path':'docs/labs/00.md','title':'Test','checkpoints':[{'id':'a','label':'A'}]}]}
        (self.root/'course-schema.json').write_text(json.dumps(schema))
        with self.assertRaises(FileNotFoundError):builder.build(self.root,self.root/'course-schema.json',self.root/'index.html')
        schema['modules'][0]['checkpoints'].append({'id':'a','label':'again'})
        with self.assertRaises(ValueError):builder.normalize(schema)
    def test_embedded_json_cannot_close_script(self):
        schema={'schema_version':1,'id':'test','review_offsets_days':[1,3,7,21],'modules':[{'id':'L00','track':'core','path':'docs/labs/00.md','title':'</script><script>evil</script>','checkpoints':[{'id':'a','label':'A'}]}]}
        (self.root/'course-schema.json').write_text(json.dumps(schema));(self.root/'docs/labs').mkdir(parents=True);(self.root/'docs/labs/00.md').write_text('# Test\n\n</script><script>evil</script>')
        builder.build(self.root,self.root/'course-schema.json',self.root/'index.html')
        result=(self.root/'index.html').read_text();self.assertNotIn('</script><script>evil',result);self.assertIn('\\u003c/script\\u003e',result)
    def test_only_exact_empty_anchors_are_preserved(self):
        rendered=self.renderer.render('<a id="s1"></a>\n\n## Source\n\n<a id="evil" onclick="alert(1)"></a>')
        self.assertIn('id="article-s1"',rendered);self.assertNotIn('<a id="evil"',rendered)
        self.assertIn('&lt;a id=',rendered)
    def test_safe_details_is_closed_and_content_is_sanitized(self):
        rendered=self.renderer.render('<details>\n<summary>Подсказка</summary>\n\n**Важно**\n<script>bad</script>\n\n```html\n</details>\n```\n</details>')
        self.assertIn('<details class="lesson-hint">',rendered);self.assertNotIn('<details open',rendered)
        self.assertIn('<summary>Подсказка</summary>',rendered);self.assertIn('<strong>Важно</strong>',rendered)
        self.assertNotIn('<script>',rendered);self.assertIn('&lt;/details&gt;',rendered)
    def test_details_attributes_are_not_whitelisted(self):
        rendered=self.renderer.render('<details onclick="bad()">\n<summary>Hint</summary>\nText\n</details>')
        self.assertNotIn('<details',rendered);self.assertIn('&lt;details',rendered)
    def test_unclosed_safe_details_fails_build(self):
        with self.assertRaises(ValueError):self.renderer.render('<details>\n<summary>Hint</summary>\nText')
    def test_duplicate_safe_anchor_rejected(self):
        with self.assertRaises(ValueError):self.renderer.render('<a id="s1"></a>\n<a id="s1"></a>')
    def test_build_is_deterministic(self):
        schema={'schema_version':1,'id':'test','review_offsets_days':[1,3,7,21],'modules':[{'id':'L00','track':'core','path':'docs/labs/00.md','title':'Test','checkpoints':[{'id':'a','label':'A'}]}]}
        (self.root/'course-schema.json').write_text(json.dumps(schema));(self.root/'docs/labs').mkdir(parents=True);(self.root/'docs/labs/00.md').write_text('# Test\n\nContent')
        builder.build(self.root,self.root/'course-schema.json',self.root/'index.html');first=(self.root/'index.html').read_bytes()
        builder.build(self.root,self.root/'course-schema.json',self.root/'index.html');self.assertEqual(first,(self.root/'index.html').read_bytes())

if __name__=='__main__':unittest.main(verbosity=2)
