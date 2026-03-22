// src/test/setup.js — Global test setup
import '@testing-library/jest-dom';

// jsdom doesn't implement scrollIntoView — stub it to prevent test failures
Element.prototype.scrollIntoView = () => {};
