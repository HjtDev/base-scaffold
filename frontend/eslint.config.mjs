import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import prettierConfig from "eslint-config-prettier";

// eslint-config-next 16 ships native flat-config arrays — no FlatCompat/eslintrc bridge
// needed. prettierConfig goes last so formatting rules from the above configs never fight
// Prettier — Prettier owns formatting, ESLint owns everything else. BASE-DESIGN.md §5.1.
const eslintConfig = [
  { ignores: [".next/**", "node_modules/**", "coverage/**"] },
  ...nextCoreWebVitals,
  prettierConfig,
];

export default eslintConfig;
