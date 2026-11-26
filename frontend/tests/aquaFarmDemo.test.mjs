import {deepEqual, match} from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';

const source = readFileSync(new URL('../src/aquaFarmDemo.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
});
const exports = {};
new Function('require', 'exports', compiled.outputText)(createRequire(import.meta.url), exports);

test('the public demo renders sample records and a sign-in exit without a session', () => {
  const html = renderToStaticMarkup(createElement(exports.AquaFarmDemo));
  match(html, /Sample Tilapia Farm/);
  match(html, /Financial institution/);
  match(html, /Platform administrator/);
  match(html, /Back to sign in/);
});

test('sample collections allocate no more than the loan balance', () => {
  deepEqual(exports.splitDemoPayment(12500, 10100, false), {loan: 10100, deposit: 2400});
  deepEqual(exports.splitDemoPayment(500, 10100, false), {loan: 500, deposit: 0});
  deepEqual(exports.splitDemoPayment(12500, 10100, true), {loan: 0, deposit: 12500});
});
