import { describe, it, expect } from 'vitest';
import { isImageFile } from '../fileHelpers';

describe('isImageFile', () => {
  it('returns false for falsy / empty values', () => {
    expect(isImageFile(null)).toBe(false);
    expect(isImageFile(undefined)).toBe(false);
    expect(isImageFile('')).toBe(false);
  });

  it('returns false for filenames without an extension', () => {
    expect(isImageFile('README')).toBe(false);
    expect(isImageFile('photo')).toBe(false);
  });

  it('recognises common image extensions', () => {
    expect(isImageFile('photo.png')).toBe(true);
    expect(isImageFile('photo.jpg')).toBe(true);
    expect(isImageFile('photo.jpeg')).toBe(true);
    expect(isImageFile('animation.gif')).toBe(true);
    expect(isImageFile('image.webp')).toBe(true);
  });

  it('excludes svg and bmp (unsupported for inline rendering)', () => {
    expect(isImageFile('icon.svg')).toBe(false);
    expect(isImageFile('bitmap.bmp')).toBe(false);
  });

  it('is case-insensitive', () => {
    expect(isImageFile('PHOTO.PNG')).toBe(true);
    expect(isImageFile('Photo.JPG')).toBe(true);
    expect(isImageFile('image.Jpeg')).toBe(true);
  });

  it('returns false for non-image extensions', () => {
    expect(isImageFile('document.pdf')).toBe(false);
    expect(isImageFile('archive.zip')).toBe(false);
    expect(isImageFile('script.js')).toBe(false);
    expect(isImageFile('styles.css')).toBe(false);
    expect(isImageFile('data.json')).toBe(false);
  });

  it('handles filenames with multiple dots', () => {
    expect(isImageFile('my.holiday.photo.jpg')).toBe(true);
    expect(isImageFile('report.v2.pdf')).toBe(false);
  });
});
