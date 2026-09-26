const fs = require('fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = fs.readFileSync('/input/PolicyNote.tsx', 'utf8');
const result = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  fileName: 'PolicyNote.tsx', reportDiagnostics: true,
});
if (result.diagnostics?.some(d => d.category === ts.DiagnosticCategory.Error)) throw new Error('Invalid TSX');
const moduleObject = {exports:{}};
const restrictedRequire = name => { if (name !== 'react') throw new Error('Only React imports supported'); return React; };
new Function('require', 'module', 'exports', result.outputText)(restrictedRequire, moduleObject, moduleObject.exports);
const html = renderToStaticMarkup(React.createElement(moduleObject.exports.default));
if (!html || html.length > 20000) throw new Error('Invalid rendered component');
fs.writeFileSync('/output/note.html', html);
