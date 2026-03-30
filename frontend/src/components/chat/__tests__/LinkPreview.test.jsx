import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import LinkPreview from '../LinkPreview';
import { previewCache } from '../../../utils/linkPreviewUtils';

// Mock the messageApi module
vi.mock('../../../services/messageApi', () => ({
  fetchLinkPreview: vi.fn(),
}));

import { fetchLinkPreview } from '../../../services/messageApi';

describe('LinkPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    previewCache.clear();
  });

  it('renders nothing when text has no URLs', () => {
    const { container } = render(<LinkPreview text="Hello, no links here!" />);
    expect(container.querySelector('.link-preview-card')).toBeNull();
  });

  it('renders nothing when text is null', () => {
    const { container } = render(<LinkPreview text={null} />);
    expect(container.querySelector('.link-preview-card')).toBeNull();
  });

  it('renders nothing when text is empty', () => {
    const { container } = render(<LinkPreview text="" />);
    expect(container.querySelector('.link-preview-card')).toBeNull();
  });

  it('shows loading state then renders preview card on success', async () => {
    fetchLinkPreview.mockResolvedValueOnce({
      data: {
        url: 'https://success-test.example.com',
        title: 'Example Domain',
        description: 'This domain is for use in examples.',
        image: 'https://success-test.example.com/img.jpg',
      },
    });

    const { container } = render(
      <LinkPreview text="Check out https://success-test.example.com for more" />
    );

    // Should call fetch
    await waitFor(() => {
      expect(fetchLinkPreview).toHaveBeenCalledWith('https://success-test.example.com');
    });

    // Wait for the preview card to render
    await waitFor(() => {
      expect(screen.getByText('Example Domain')).toBeInTheDocument();
    });

    expect(screen.getByText('This domain is for use in examples.')).toBeInTheDocument();
    expect(screen.getByText('success-test.example.com')).toBeInTheDocument();

    // Check that image is rendered
    const img = container.querySelector('.link-preview-image');
    expect(img).not.toBeNull();
    expect(img.src).toBe('https://success-test.example.com/img.jpg');

    // Check that link opens in new tab
    const link = container.querySelector('a.link-preview-card');
    expect(link).not.toBeNull();
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
  });

  it('renders nothing when fetch fails', async () => {
    fetchLinkPreview.mockRejectedValueOnce(new Error('Network error'));

    const { container } = render(
      <LinkPreview text="Visit https://bad-url-unique.example.com" />
    );

    await waitFor(() => {
      expect(fetchLinkPreview).toHaveBeenCalled();
    });

    // Wait for the loading state to clear
    await waitFor(() => {
      expect(container.querySelector('.link-preview-loading')).toBeNull();
    });

    // Should not render any preview card
    expect(container.querySelector('.link-preview-card')).toBeNull();
  });

  it('renders card without image when image is null', async () => {
    fetchLinkPreview.mockResolvedValueOnce({
      data: {
        url: 'https://no-image-test.example.com',
        title: 'No Image',
        description: 'A page without an image.',
        image: null,
      },
    });

    const { container } = render(
      <LinkPreview text="https://no-image-test.example.com" />
    );

    await waitFor(() => {
      expect(screen.getByText('No Image')).toBeInTheDocument();
    });

    // No image element should be rendered
    expect(container.querySelector('.link-preview-image')).toBeNull();
  });

  it('strips www from domain display', async () => {
    fetchLinkPreview.mockResolvedValueOnce({
      data: {
        url: 'https://www.www-test.example.com',
        title: 'WWW Test',
        description: null,
        image: null,
      },
    });

    render(<LinkPreview text="https://www.www-test.example.com/page" />);

    await waitFor(() => {
      expect(screen.getByText('www-test.example.com')).toBeInTheDocument();
    });
  });

  it('extracts only the first URL from text with multiple URLs', async () => {
    fetchLinkPreview.mockResolvedValueOnce({
      data: {
        url: 'https://first-multi.example.com',
        title: 'First URL',
        description: null,
        image: null,
      },
    });

    render(<LinkPreview text="https://first-multi.example.com and https://second-multi.example.com" />);

    await waitFor(() => {
      expect(fetchLinkPreview).toHaveBeenCalledWith('https://first-multi.example.com');
    });

    // Should not have been called with the second URL
    expect(fetchLinkPreview).not.toHaveBeenCalledWith('https://second-multi.example.com');
  });

  it('uses cached data on subsequent renders', async () => {
    fetchLinkPreview.mockResolvedValueOnce({
      data: {
        url: 'https://cache-reuse-test.example.com',
        title: 'Cached Page',
        description: 'Should be cached',
        image: null,
      },
    });

    // First render — triggers fetch
    const { unmount } = render(
      <LinkPreview text="https://cache-reuse-test.example.com" />
    );

    await waitFor(() => {
      expect(screen.getByText('Cached Page')).toBeInTheDocument();
    });

    expect(fetchLinkPreview).toHaveBeenCalledTimes(1);

    // Unmount and re-render — should use cache
    unmount();

    render(<LinkPreview text="https://cache-reuse-test.example.com" />);

    await waitFor(() => {
      expect(screen.getByText('Cached Page')).toBeInTheDocument();
    });

    // Should NOT have fetched again
    expect(fetchLinkPreview).toHaveBeenCalledTimes(1);
  });
});
