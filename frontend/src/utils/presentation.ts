// String-only formatting preserves cents even beyond Number.MAX_SAFE_INTEGER.
export function decimal(value: string): string {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) return "—";
  return `${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${(match[3] ?? "").padEnd(2, "0")}`;
}
export const money = (value: string | null, currency: string | null) =>
  value === null || !currency ? "—" : `${decimal(value)} ${currency}`;
export const dateLabel = (value: string) =>
  new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value.slice(0, 10) + "T12:00:00Z"));
export const monthLabel = (value: string) =>
  new Intl.DateTimeFormat("tr-TR", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value + "-01T12:00:00Z"));
export const categoryLabels: Record<string, string> = {
  GROCERIES: "Market",
  RESTAURANTS: "Restoran",
  CAFE: "Kafe",
  FOOD_DELIVERY: "Yemek siparişi",
  TRANSPORTATION: "Ulaşım",
  FUEL: "Akaryakıt",
  SHOPPING: "Alışveriş",
  ENTERTAINMENT: "Eğlence",
  SUBSCRIPTIONS: "Abonelikler",
  BILLS: "Faturalar",
  HOUSING: "Konut",
  HEALTH: "Sağlık",
  EDUCATION: "Eğitim",
  TRAVEL: "Seyahat",
  FINANCIAL_FEES: "Finansal ücretler",
  INCOME: "Gelir",
  TRANSFER: "Transfer",
  OTHER: "Diğer",
};
export const categoryLabel = (code: string) =>
  categoryLabels[code] ?? "Diğer kategori";
export const typeLabels = {
  EXPENSE: "Harcama",
  REFUND: "İade",
  TRANSFER: "Transfer",
  CARD_PAYMENT: "Kart ödemesi",
  INCOME: "Gelir",
  FEE: "Finansal ücret",
  CASH_WITHDRAWAL: "Nakit çekim",
  INTEREST: "Faiz",
  UNKNOWN: "Belirsiz",
};
export const reviewLabels = {
  NEEDS_REVIEW: "İnceleme bekliyor",
  AUTO_CONFIRMED: "Otomatik sınıflandırıldı",
  USER_CONFIRMED: "Kullanıcı onaylı",
};
export const importLabels = {
  PENDING: "İşleniyor",
  PARSED: "Okundu",
  AWAITING_CONFIRMATION: "Onay bekliyor",
  COMPLETED: "Tamamlandı",
  FAILED: "Doğrulanamadı",
};
export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function monthPeriod(now: Date, offset = 0) {
  return {
    start_date: isoDate(
      new Date(now.getFullYear(), now.getMonth() + offset, 1),
    ),
    end_date: isoDate(
      new Date(now.getFullYear(), now.getMonth() + offset + 1, 0),
    ),
  };
}
export function precedingPeriod(start: string, end: string) {
  const startTime = Date.parse(start + "T12:00:00Z"),
    endTime = Date.parse(end + "T12:00:00Z");
  const date = (time: number) => new Date(time).toISOString().slice(0, 10);
  return {
    start_date: date(startTime - (endTime - startTime) - 86400000),
    end_date: date(startTime - 86400000),
  };
}
