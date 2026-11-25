import {deepEqual, doesNotMatch, match} from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/institutionReviewPages.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
});
const exports = {};
new Function('require', 'exports', compiled.outputText)(require, exports);
const {InstitutionReviewPages} = exports;

const rows = [
  {id: 1, name: 'Pending Bank', status: 'under_review', institution_type: 'bank', registration_number: 'P1'},
  {id: 2, name: 'Approved Bank', status: 'verified', institution_type: 'bank', registration_number: 'A2'},
  {id: 3, name: 'Rejected Bank', status: 'rejected', institution_type: 'bank', registration_number: 'R3'},
  {id: 4, name: 'Suspended Bank', status: 'suspended', institution_type: 'bank', registration_number: 'S4'},
];
const render = (view, options = {}) => renderToStaticMarkup(createElement(InstitutionReviewPages, {
  view: 'institutions'+view, rows, search: '', setSearch() {}, busy: false, owner: false, decide() {}, ...options,
}));

test('institution landing has linked counts and no record details', () => {
  const html = render('');
  match(html, /Pending institution approvals \(1\)/);
  match(html, /All financial institutions \(4\)/);
  match(html, /#admin\/institutions\/register/);
  doesNotMatch(html, /Pending Bank/);
});

test('status directories constrain search to the selected workflow', () => {
  const pages = ['/pending', '/verified', '/rejected', '/suspended'];
  deepEqual(pages.map(page => rows.filter(row => render(page).includes(row.name)).map(row => row.id)), [[1], [2], [3], [4]]);
  match(render('/pending', {search: 'Approved Bank'}), /No institutions match/);
});

test('decision actions appear only on the review destination and respect the owner role', () => {
  doesNotMatch(render('/details/1'), />Approve<|>Reject</);
  match(render('/review/1'), />Approve<.*>Reject</);
  doesNotMatch(render('/review/2'), />Suspend</);
  match(render('/review/2', {owner: true}), />Suspend</);
});
