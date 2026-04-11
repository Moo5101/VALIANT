export function normalizePhone(value: string): string {
  const cleaned = value.replace(/[^\d+]/g, "").trim();
  if (!cleaned) {
    return "";
  }

  if (cleaned.startsWith("+")) {
    return `+${cleaned.slice(1).replace(/\D/g, "")}`;
  }

  const digitsOnly = cleaned.replace(/\D/g, "");
  if (digitsOnly.length === 10) {
    return `+1${digitsOnly}`;
  }
  if (digitsOnly.length === 11 && digitsOnly.startsWith("1")) {
    return `+${digitsOnly}`;
  }
  return digitsOnly ? `+${digitsOnly}` : "";
}
