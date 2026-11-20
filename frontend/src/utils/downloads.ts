export function downloadBlob(content: Blob, filename: string): void {
  const href = URL.createObjectURL(content);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export function filenameFromContentDisposition(header?: string | null, fallback = "download"): string {
  if (!header) return fallback;
  const match = /filename="?([^"]+)"?/i.exec(header);
  return match?.[1] ?? fallback;
}
