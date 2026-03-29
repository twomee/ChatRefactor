import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MarkdownMessage from '../MarkdownMessage';

describe('MarkdownMessage', () => {
  it('renders nothing when text is empty', () => {
    const { container } = render(<MarkdownMessage text="" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when text is null', () => {
    const { container } = render(<MarkdownMessage text={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders plain text', () => {
    render(<MarkdownMessage text="Hello world" />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('renders bold text from **markdown**', () => {
    const { container } = render(<MarkdownMessage text="**bold**" />);
    expect(container.querySelector('strong')).toBeInTheDocument();
    expect(container.querySelector('strong').textContent).toBe('bold');
  });

  it('renders italic text from _markdown_', () => {
    const { container } = render(<MarkdownMessage text="_italic_" />);
    expect(container.querySelector('em')).toBeInTheDocument();
  });

  it('renders inline code with inline-code class', () => {
    const { container } = render(<MarkdownMessage text="`code`" />);
    expect(container.querySelector('code.inline-code')).toBeInTheDocument();
  });

  it('renders fenced code blocks with code-block class', () => {
    const { container } = render(
      <MarkdownMessage text={'```javascript\nconst x = 1;\n```'} />
    );
    expect(container.querySelector('pre.code-block')).toBeInTheDocument();
    expect(container.querySelector('pre.code-block code')).toBeInTheDocument();
  });

  it('renders links with target=_blank and noopener noreferrer', () => {
    const { container } = render(
      <MarkdownMessage text="[click here](https://example.com)" />
    );
    const link = container.querySelector('a');
    expect(link).toBeInTheDocument();
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.getAttribute('href')).toBe('https://example.com');
  });

  it('renders strikethrough with GFM ~~text~~', () => {
    const { container } = render(<MarkdownMessage text="~~strikethrough~~" />);
    expect(container.querySelector('del')).toBeInTheDocument();
  });
});
