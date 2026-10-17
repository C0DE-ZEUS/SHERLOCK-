export const ACCEPTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];
export const ACCEPT_ATTR = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

/** Quick client-side check for instant feedback. The backend re-validates
 *  everything (extension, MIME type and file signature). */
export function validateFile(file: File, maxMb: number): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Unsupported file type. Upload a PDF, PNG, JPG, or JPEG file.";
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > maxMb * 1024 * 1024) return `This file is larger than the ${maxMb} MB limit.`;
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
