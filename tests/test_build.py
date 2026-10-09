#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock
import re

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
    def test_source_title_anchor_preserves_semantic_heading_levels(self):
        rendered=self.renderer.render('# Source title\n\n## Experiment\n\n### Check\n\nParagraph')
        self.assertIn('class="anchor-target source-title" id="article-source-title"',rendered)
        self.assertNotIn('<h1',rendered)
        self.assertIn('<h2 id="article-experiment">Experiment</h2>',rendered)
        self.assertIn('<h3 id="article-check">Check</h3>',rendered)
        self.assertEqual([h['level'] for h in self.renderer.headings],[1,2,3])
    def test_section_without_source_title_is_not_demoted_or_hidden(self):
        rendered=self.renderer.render('## First section\nText')
        self.assertTrue(rendered.startswith('<h2 id="article-first-section">'))
    def test_code_wrap_control_is_explicit_and_code_is_unchanged(self):
        rendered=self.renderer.render('```c\nint answer = 42;\n```')
        self.assertIn('class="wrap-code" aria-pressed="false"',rendered)
        self.assertIn('role="region" aria-label="Код, прокручивается по горизонтали"',rendered)
        self.assertIn('<code class="language-c">int answer = 42;</code>',rendered)
    def test_nested_hints_start_closed_and_keep_their_hierarchy(self):
        rendered=self.renderer.render('<details>\n<summary>Hint 1</summary>\n\n<details>\n<summary>Hint 2</summary>\n\n## Explanation\n\n</details>\n</details>')
        self.assertEqual(rendered.count('<details class="lesson-hint">'),2)
        self.assertEqual(rendered.count('</details>'),2)
        self.assertNotIn('<details open',rendered)
        self.assertIn('<h2 id="article-explanation">',rendered)
    def test_safe_hint_is_a_block_even_without_blank_line(self):
        rendered=self.renderer.render('Make a prediction.\n<details>\n<summary>Compare after an attempt</summary>\n\nFeedback.\n</details>')
        self.assertIn('</p>\n<details class="lesson-hint">',rendered)
        self.assertNotIn('&lt;summary&gt;',rendered)
    def test_long_fence_inside_hint_does_not_close_on_short_fence(self):
        rendered=self.renderer.render('<details>\n<summary>Hint</summary>\n\n````text\n```\n</details>\n````\n\nActual feedback.\n</details>')
        self.assertEqual(rendered.count('<details class="lesson-hint">'),1)
        self.assertIn('&lt;/details&gt;',rendered)
        self.assertIn('Actual feedback.',rendered)
    def test_details_summary_is_escaped_and_has_no_active_html(self):
        rendered=self.renderer.render('<details>\n<summary>**After** & before</summary>\n\n[bad](javascript:alert)\n</details>')
        self.assertIn('<summary><strong>After</strong> &amp; before</summary>',rendered)
        self.assertNotIn('href="javascript:',rendered)
    def test_build_is_deterministic(self):
        schema={'schema_version':1,'id':'test','review_offsets_days':[1,3,7,21],'modules':[{'id':'L00','track':'core','path':'docs/labs/00.md','title':'Test','checkpoints':[{'id':'a','label':'A'}]}]}
        (self.root/'course-schema.json').write_text(json.dumps(schema));(self.root/'docs/labs').mkdir(parents=True);(self.root/'docs/labs/00.md').write_text('# Test\n\nContent')
        builder.build(self.root,self.root/'course-schema.json',self.root/'index.html');first=(self.root/'index.html').read_bytes()
        builder.build(self.root,self.root/'course-schema.json',self.root/'index.html');self.assertEqual(first,(self.root/'index.html').read_bytes())

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.parent=pathlib.Path(self.tmp.name);self.root=self.parent/'repo';self.root.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def write(self,path,content):
        target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8');return target
    def schema(self):
        schema={'schema_version':1,'id':'test','modules':[{'id':'L00','number':0,'track':'core','path':'docs/labs/00.md','title':'Test','checkpoints':[{'id':'a','label':'A'}]}]}
        return self.write('course-schema.json',json.dumps(schema))
    def test_transitive_exercise_and_tool_guides_with_cycles_are_bounded(self):
        self.write('docs/labs/00.md','# Start\n\n[Exercise](../../examples/digital/transfer-guard/README.md#after)')
        self.write('examples/digital/transfer-guard/README.md','# Exercise\n\n## After\n\n[Tool](../../../tools/README-project-check.md) [Back](../../../docs/labs/00.md) [C](student.c)')
        self.write('tools/README-project-check.md','# Project check\n\n[Back](../docs/labs/00.md)')
        self.write('examples/digital/transfer-guard/student.c','not Markdown and never embedded')
        self.write('unrelated/private.md','# Must stay out')
        sources,initial,missing=builder.discover_markdown(self.root,{'docs/labs/00.md'})
        self.assertEqual(set(sources),{'docs/labs/00.md','examples/digital/transfer-guard/README.md','tools/README-project-check.md'})
        self.assertEqual(initial,{'docs/labs/00.md'});self.assertEqual(missing,[])
        again=builder.discover_markdown(self.root,{'docs/labs/00.md'})
        self.assertEqual(list(sources),list(again[0]))
    def test_missing_linked_markdown_fails_closed_and_preview_is_explicit(self):
        self.write('docs/start.md','# Start\n\n[Missing](missing.md)')
        with self.assertRaisesRegex(FileNotFoundError,'docs/missing.md'):builder.discover_markdown(self.root,{'docs/start.md'})
        sources,_,missing=builder.discover_markdown(self.root,{'docs/start.md'},allow_missing=True)
        self.assertEqual(missing,['docs/missing.md']);self.assertIn('Материал ожидает интеграции',sources['docs/missing.md'])
    def test_traversal_and_encoded_traversal_never_read_outside_root(self):
        (self.parent/'outside.md').write_text('PRIVATE OUTSIDE')
        for target in ['../../outside.md','..%2F..%2Foutside.md',str(self.parent/'outside.md')]:
            self.write('docs/start.md','# Start\n\n[Outside]('+target+')')
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'leaves repository'):
                builder.discover_markdown(self.root,{'docs/start.md'})
    def test_outside_symlinks_are_rejected_for_links_and_seed_sources(self):
        outside=self.parent/'outside.md';outside.write_text('PRIVATE OUTSIDE')
        self.write('docs/start.md','# Start\n\n[Outside](alias.md)')
        (self.root/'docs/alias.md').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'leaves repository'):builder.discover_markdown(self.root,{'docs/start.md'})
        with self.assertRaisesRegex(ValueError,'outside repository'):builder.discover_markdown(self.root,{'docs/alias.md'})
    def test_outside_directory_symlink_is_never_followed(self):
        outside=self.parent/'outside';outside.mkdir();(outside/'secret.md').write_text('PRIVATE OUTSIDE')
        (self.root/'examples').symlink_to(outside,target_is_directory=True)
        self.write('docs/start.md','# Start\n\n[Outside](../examples/secret.md)')
        with self.assertRaisesRegex(ValueError,'leaves repository'):builder.discover_markdown(self.root,{'docs/start.md'})
    def test_code_and_raw_html_links_are_not_discovery_instructions(self):
        self.write('docs/start.md','# Start\n\n`[Inline](missing-inline.md)`\n\n````text\n[Code](missing-code.md)\n````\n\n<a href="missing-html.md">Raw</a>\n\n[Web](https://example.com/never-fetch.md)')
        sources,_,_=builder.discover_markdown(self.root,{'docs/start.md'})
        self.assertEqual(list(sources),['docs/start.md'])
    def test_markdown_looking_image_targets_are_not_included(self):
        self.write('docs/start.md','# Start\n\n![Wrong format](extra.md) ![Missing](missing.md) ![Outside](../../outside.md)')
        self.write('docs/extra.md','# Unlinked guide')
        (self.parent/'outside.md').write_text('PRIVATE OUTSIDE')
        sources,_,_=builder.discover_markdown(self.root,{'docs/start.md'})
        self.assertEqual(list(sources),['docs/start.md'])
    def test_explicit_file_count_and_byte_limits(self):
        self.write('docs/a.md','# A\n\n[B](b.md)');self.write('docs/b.md','# B\n\n[C](c.md)');self.write('docs/c.md','# C')
        with mock.patch.object(builder,'MAX_MARKDOWN_FILES',2),self.assertRaisesRegex(ValueError,'exceeds 2 files'):
            builder.discover_markdown(self.root,{'docs/a.md'})
        with mock.patch.object(builder,'MAX_MARKDOWN_FILE_BYTES',5),self.assertRaisesRegex(ValueError,'per-file size limit'):
            builder.discover_markdown(self.root,{'docs/a.md'})
        with mock.patch.object(builder,'MAX_MARKDOWN_TOTAL_BYTES',20),self.assertRaisesRegex(ValueError,'total size limit'):
            builder.discover_markdown(self.root,{'docs/a.md'})
    def test_guides_become_embedded_routes_but_code_downloads_do_not_change(self):
        self.write('docs/labs/00.md','# Start\n\n[Guide](../../tools/README-project-check.md#usage) [Code](../../tools/check_project.py)')
        self.write('tools/README-project-check.md','# Project check\n\n## Usage\n\n[Back](../docs/labs/00.md)')
        self.write('tools/check_project.py','print("test")')
        schema=self.schema();out=self.root/'index.html';builder.build(self.root,schema,out)
        data=json.loads(re.search(r'<script id="course-data" type="application/json">(.*?)</script>',out.read_text(),re.S)[1])
        self.assertEqual(len(data['documents']),1);guide=data['documents'][0]
        self.assertEqual(guide['path'],'tools/README-project-check.md');self.assertTrue(guide['linked_only'])
        self.assertIn('#section/document/tools/README-project-check.md/usage',data['modules'][0]['html'])
        self.assertIn('href="tools/check_project.py"',data['modules'][0]['html'])
        self.assertNotIn('print(&quot;test&quot;)',out.read_text())
    def test_discovery_failure_does_not_overwrite_an_existing_release(self):
        self.write('docs/labs/00.md','# Start\n\n[Missing](missing.md)');schema=self.schema();out=self.write('index.html','EXISTING RELEASE')
        with self.assertRaises(FileNotFoundError):builder.build(self.root,schema,out)
        self.assertEqual(out.read_text(),'EXISTING RELEASE')

if __name__=='__main__':unittest.main(verbosity=2)
