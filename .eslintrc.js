module.exports = {
    env: {
        browser: true,
        es2021: true,
    },
    extends: ['eslint:recommended', 'prettier'],
    parserOptions: {
        ecmaVersion: 2021,
        sourceType: 'module',
    },
    rules: {
        'no-console': ['warn', { allow: ['warn', 'error'] }],
        'no-unused-vars': 'warn',
    },
};
