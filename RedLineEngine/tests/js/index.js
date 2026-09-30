// Compatibility shim: Node 21+ (verified on v25.8.1) treats a directory
// argument to `node --test` as a module path instead of expanding it to the
// test files inside (nodejs/node#64555), so `node --test tests/js` fails with
// MODULE_NOT_FOUND. This index file makes that exact command work by loading
// the real test file; glob invocations (`node --test "tests/js/*.test.mjs"`)
// and bare `node --test` discovery are unaffected and do not match this file.
require("./app_util.test.mjs");
require("./busy.test.mjs");
require("./rack_state.test.mjs");
require("./plugin_state.test.mjs");
