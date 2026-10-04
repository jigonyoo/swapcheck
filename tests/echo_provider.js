// Deterministic local provider: no network, no API key.
// "before" answers correctly; "after" leaks an email on one case and is wrong on another.
module.exports = class EchoProvider {
  constructor(options) { this.variant = options.config.variant; this.label = options.label; }
  id() { return `local:${this.variant}`; }
  async callApi(prompt, context) {
    const q = context.vars.question;
    const rep = context.vars.__repeatIndex ?? 0;
    let out = `Answer: ${context.vars.expected}`;
    if (this.variant === 'after' && q.includes('refund')) out += ' contact jane@example.com';
    if (this.variant === 'after' && q.includes('weather') && rep === 1) out = 'Answer: unsure';
    return { output: out, cost: this.variant === 'after' ? 0.0004 : 0.001, latencyMs: this.variant === 'after' ? 120 : 300 };
  }
};
