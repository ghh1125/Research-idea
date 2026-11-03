"""Exercise the actual browser renderer with Node when available; no DOM libraries."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is optional for renderer checks')
class FrontendTests(unittest.TestCase):
    def test_markdown_links_code_and_report_disclosures_are_safe_and_readable(self):
        source = Path(__file__).resolve().parents[1] / 'src/research_idea/web_assets/app.js'
        script = r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const code=fs.readFileSync(process.argv[1],'utf8').split('async function api(')[0];
const context=vm.createContext({}); vm.runInContext(code,context);
const render=text=>vm.runInContext('markdown('+JSON.stringify(text)+')',context);
const safe=render('<script>alert(1)</script>\n\n[paper](https://example.org/\"onclick=\"evil)');
assert(safe.includes('&lt;script&gt;'));
assert(!safe.includes('<script>'));
assert(!safe.includes('href="https://example.org/"onclick='));
const example=render('`[paper](https://example.org)`');
assert(example.includes('<code>[paper](https://example.org)</code>'));
assert(!example.includes('<a '));
const links=render('[paper](https://example.org/?a=1&b=2) and https://example.org/paper');
assert(links.includes('href="https://example.org/?a=1&amp;b=2"'));
assert.equal((links.match(/<a /g)||[]).length,2);
const detail=render('<details>\n<summary>原文依据</summary>\n\n正文\n\n</details>');
assert(detail.includes('<details class="report-detail"><summary>原文依据</summary>'));
assert(!detail.includes('&lt;details&gt;'));
assert(render('<details onclick="evil">').includes('&lt;details onclick='));
'''
        subprocess.run(['node', '-e', script, str(source)], check=True, capture_output=True, text=True)
