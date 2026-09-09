import lichtblick from "@lichtblick/eslint-plugin";
import globals from "globals";

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "*.foxe",
      "config.ts",
      "eslint.config.mjs",
    ],
  },
  ...lichtblick.configs.base,
  ...lichtblick.configs.react,
  ...lichtblick.configs.typescript,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { projectService: true },
    },
    rules: {
      "@lichtblick/license-header": "off",
      "@typescript-eslint/no-confusing-void-expression": "off",
      "@typescript-eslint/promise-function-async": "off",
      "@typescript-eslint/return-await": "off",
    },
  },
];
