import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MarkdownMessage from '../MarkdownMessage';

describe('MarkdownMessage', () => {
  it('returns null for empty text', () => {
    const { container } = render(<MarkdownMessage text="" />);
    expect(container.innerHTML).toBe('');
  });

  it('returns null for undefined text', () => {
    const { container } = render(<MarkdownMessage text={undefined} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders plain text without markdown', () => {
    render(<MarkdownMessage text="Hello world" />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('renders bold text', () => {
    const { container } = render(<MarkdownMessage text="**bold text**" />);
    const strong = container.querySelector('strong');
    expect(strong).toBeInTheDocument();
    expect(strong.textContent).toBe('bold text');
  });

  it('renders italic text', () => {
    const { container } = render(<MarkdownMessage text="*italic text*" />);
    const em = container.querySelector('em');
    expect(em).toBeInTheDocument();
    expect(em.textContent).toBe('italic text');
  });

  it('renders inline code with correct class', () => {
    const { container } = render(<MarkdownMessage text="`inline code`" />);
    const code = container.querySelector('code.inline-code');
    expect(code).toBeInTheDocument();
    expect(code.textContent).toBe('inline code');
  });

  it('renders fenced code blocks with correct class', () => {
    const { container } = render(<MarkdownMessage text={'```\ncode block\n```'} />);
    const pre = container.querySelector('.code-block');
    expect(pre).toBeInTheDocument();
  });

  it('renders links with target _blank and noopener', () => {
    const { container } = render(<MarkdownMessage text="[link](https://example.com)" />);
    const a = container.querySelector('a');
    expect(a).toBeInTheDocument();
    expect(a).toHaveAttribute('target', '_blank');
    expect(a).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('strips disallowed HTML elements', () => {
    const { container } = render(<MarkdownMessage text='<img src="x" onerror="alert(1)">' />);
    const img = container.querySelector('img');
    expect(img).not.toBeInTheDocument();
  });

  it('sanitizes javascript: href', () => {
    const { container } = render(<MarkdownMessage text='[click](javascript:alert(1))' />);
    const a = container.querySelector('a');
    // react-markdown sanitizes javascript: URIs by default
    if (a) {
      expect(a.getAttribute('href')).not.toContain('javascript:');
    }
  });

  it('renders blockquotes', () => {
    const { container } = render(<MarkdownMessage text="> quoted text" />);
    const bq = container.querySelector('blockquote');
    expect(bq).toBeInTheDocument();
  });

  it('renders strikethrough (GFM)', () => {
    const { container } = render(<MarkdownMessage text="~~deleted~~" />);
    const del = container.querySelector('del');
    expect(del).toBeInTheDocument();
  });
});
