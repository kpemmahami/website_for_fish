import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('./src/apiBase.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext}});
const {resolveApiBase} = await import('data:text/javascript,' + encodeURIComponent(outputText));

test('farmer registration uses the configured hosted API origin', () => {
 assert.equal(resolveApiBase(' https://api.example.invalid/ ')+'/auth/farmer/register',
              'https://api.example.invalid/auth/farmer/register');
});

test('local and same-origin deployments retain the proxy path', () => {
 assert.equal(resolveApiBase(undefined)+'/auth/farmer/register','/api/auth/farmer/register');
 assert.equal(resolveApiBase(' '),'/api');
});

test('reject credentials, query strings and non-HTTP API URLs', () => {
 for(const unsafe of ['https://user:secret@api.example.invalid','https://api.example.invalid?secret=1','file:///api']){
  assert.throws(()=>resolveApiBase(unsafe));
 }
});
