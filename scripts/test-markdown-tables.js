#!/usr/bin/env node

/**
 * Manual verification script for markdown-parser.ts table handling
 *
 * Usage: node scripts/test-markdown-tables.js
 *
 * This script verifies that:
 * 1. GFM pipe tables work correctly despite breaks: true
 * 2. HTML tables are properly escaped
 * 3. Edge cases are handled gracefully
 */

const { marked } = require('marked');

function escapeHtml(raw) {
    return (raw || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Configure marked exactly as in markdown-parser.ts
marked.setOptions({
    mangle: false,
    headerIds: false,
    gfm: true,
    breaks: true,
});

marked.use({
    renderer: {
        html(token) {
            return escapeHtml(token?.text || '');
        },
    },
});

// Test cases
const tests = [
    {
        name: 'Simple pipe table',
        markdown: '| Col1 | Col2 |\n|------|------|\n| A    | B    |',
        expectations: [
            { check: (html) => html.includes('<table>'), desc: 'should have <table>' },
            { check: (html) => html.includes('<thead>'), desc: 'should have <thead>' },
            { check: (html) => html.includes('Col1'), desc: 'should have header Col1' },
        ],
    },
    {
        name: 'Multi-row table',
        markdown: '| Name | Age |\n|------|-----|\n| John | 25  |\n| Jane | 30  |',
        expectations: [
            { check: (html) => html.includes('John'), desc: 'should have John' },
            { check: (html) => html.includes('30'), desc: 'should have 30' },
            { check: (html) => (html.match(/<td>/g) || []).length >= 4, desc: 'should have at least 4 cells' },
        ],
    },
    {
        name: 'Table + paragraph separation',
        markdown: '| Col1 | Col2 |\n|------|------|\n| A    | B    |\n\nParagraph here',
        expectations: [
            { check: (html) => html.includes('<table>'), desc: 'should have table' },
            { check: (html) => html.includes('<p>'), desc: 'should have paragraph' },
            { check: (html) => html.includes('Paragraph here'), desc: 'should have paragraph text' },
        ],
    },
    {
        name: 'HTML table (security test)',
        markdown: '<table><tr><td>A</td><td>B</td></tr></table>',
        expectations: [
            { check: (html) => html.includes('&lt;table&gt;'), desc: 'should escape <table>' },
            { check: (html) => !html.match(/<table>/), desc: 'should NOT have unescaped <table>' },
        ],
    },
    {
        name: 'Complex markdown + table',
        markdown: '# Header\n\nText\n\n| Key | Value |\n|-----|-------|\n| Foo | 100   |\n\nEnd',
        expectations: [
            { check: (html) => html.includes('<h1>'), desc: 'should have header' },
            { check: (html) => html.includes('<table>'), desc: 'should have table' },
            { check: (html) => html.includes('Foo'), desc: 'should have table content' },
        ],
    },
];

// Run tests
console.log('\n' + '='.repeat(80));
console.log('Markdown Parser — Table Handling Tests');
console.log('='.repeat(80));

let passed = 0;
let failed = 0;

tests.forEach((test, idx) => {
    console.log(`\n[Test ${idx + 1}] ${test.name}`);
    console.log('-'.repeat(80));

    try {
        const html = marked.parse(test.markdown, { async: false });

        let testPassed = true;
        test.expectations.forEach((expectation) => {
            const result = expectation.check(html);
            const status = result ? '✓' : '✗';
            console.log(`  ${status} ${expectation.desc}`);
            if (!result) {
                testPassed = false;
            }
        });

        if (testPassed) {
            console.log(`✓ PASS`);
            passed++;
        } else {
            console.log(`✗ FAIL`);
            failed++;
            console.log('\nHTML Output:');
            console.log(html.substring(0, 200) + (html.length > 200 ? '...' : ''));
        }
    } catch (err) {
        console.log(`✗ ERROR: ${err.message}`);
        failed++;
    }
});

// Summary
console.log('\n' + '='.repeat(80));
console.log(`Results: ${passed} passed, ${failed} failed out of ${tests.length}`);
console.log('='.repeat(80) + '\n');

process.exit(failed > 0 ? 1 : 0);
