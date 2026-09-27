WebSdk.Client - client side SDK allowing communication with server-side WebSdk plugin from web pages.

/src/ - source code
/src/libs - third-party libraries
/dts/websdk.client.d.ts - module definition to be used with TypeScript

/websdk.client.bundle.js - automatically generated bundle of all js-files from /src

/bundleconfig.json - to build the library, use the "Bundler and Minifier" VS extension by Mads Kristensen
                    (https://marketplace.visualstudio.com/items?itemName=MadsKristensen.BundlerMinifier).
                    Right-click on the bundleconfig.json and choose "Update bundles" to rebuild bundles
                    in the /dist folder.