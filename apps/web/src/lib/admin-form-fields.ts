import type { AdminVariant } from './admin-catalog-client';

export type HardwareKind = AdminVariant['specifications']['kind'];
export type SpecField = { key: string; fa: string; en: string; type?: 'number' | 'boolean' | 'list' | 'counts'; options?: readonly string[]; required?: boolean };
const field = (key: string, fa: string, en: string, type?: SpecField['type']): SpecField => ({ key, fa, en, type });
const generation = (key: string): SpecField => ({ key, fa: 'نسل حافظه', en: 'Memory generation', options: ['DDR4', 'DDR5'] });
const socket = field('socket', 'سوکت', 'Socket');
const form = field('form_factor', 'فرم فاکتور', 'Form factor');
const capacity = field('capacity_gb', 'ظرفیت (گیگابایت)', 'Capacity (GB)', 'number');
const length = field('length_mm', 'طول (میلی‌متر)', 'Length (mm)', 'number');
const height = field('height_mm', 'ارتفاع (میلی‌متر)', 'Height (mm)', 'number');
const maxMemory = field('max_memory_gb', 'حداکثر حافظه (گیگابایت)', 'Maximum memory (GB)', 'number');
export const hardwareLabels: Record<HardwareKind, readonly [string, string]> = {
  cpu: ['پردازنده', 'Processor'], motherboard: ['مادربرد', 'Motherboard'], memory: ['حافظهٔ رم', 'Memory'], storage: ['ذخیره‌سازی', 'Storage'], case: ['کیس', 'Case'], psu: ['منبع تغذیه', 'Power supply'], cooler: ['خنک‌کننده', 'Cooler'], gpu: ['کارت گرافیک', 'Graphics card'], peripheral: ['تجهیزات جانبی', 'Peripheral'], prebuilt: ['سیستم آماده', 'Prebuilt PC'],
};
export const specFields: Record<HardwareKind, readonly SpecField[]> = {
  cpu: [{ ...field('model', 'مدل دقیق پردازنده', 'Exact CPU model'), required: true }, socket, generation('memory_generation'), maxMemory, field('cores', 'تعداد هسته', 'Cores', 'number'), field('threads', 'تعداد رشته', 'Threads', 'number'), field('tdp_w', 'توان طراحی حرارتی (وات)', 'Thermal design power (W)', 'number'), field('max_package_power_w', 'حداکثر توان پکیج (وات)', 'Maximum package power (W)', 'number'), field('integrated_graphics', 'گرافیک مجتمع', 'Integrated graphics', 'boolean'), field('included_cooler', 'خنک‌کنندهٔ همراه', 'Included cooler', 'boolean'), field('included_cooler_height_mm', 'ارتفاع خنک‌کنندهٔ همراه (میلی‌متر)', 'Included cooler height (mm)', 'number')],
  motherboard: [socket, form, generation('memory_generation'), field('memory_slots', 'تعداد اسلات حافظه', 'Memory slots', 'number'), maxMemory, field('bios_revision', 'نسخهٔ بایوس', 'BIOS revision'), field('verified_bios_revision', 'نسخهٔ بایوس بررسی‌شده', 'Verified BIOS revision'), field('verified_cpu_models', 'مدل‌های پردازندهٔ بررسی‌شده', 'Verified CPU models', 'list'), field('storage_interfaces', 'رابط‌های ذخیره‌سازی و تعداد', 'Storage interfaces and counts', 'counts'), field('storage_form_factors', 'اندازه‌های ذخیره‌سازی پشتیبانی‌شده', 'Supported storage forms', 'list'), field('power_connectors', 'کانکتورهای برق و تعداد', 'Power connectors and counts', 'counts')],
  memory: [generation('generation'), field('modules', 'تعداد ماژول', 'Modules', 'number'), capacity, height],
  storage: [field('interface', 'رابط اتصال', 'Interface'), form, capacity],
  case: [field('motherboard_forms', 'فرم‌های مادربرد', 'Motherboard forms', 'list'), field('psu_forms', 'فرم‌های منبع تغذیه', 'Power supply forms', 'list'), field('max_psu_length_mm', 'حداکثر طول منبع تغذیه (میلی‌متر)', 'Maximum PSU length (mm)', 'number'), field('max_gpu_length_mm', 'حداکثر طول کارت گرافیک (میلی‌متر)', 'Maximum GPU length (mm)', 'number'), field('max_gpu_height_mm', 'حداکثر ارتفاع کارت گرافیک (میلی‌متر)', 'Maximum GPU height (mm)', 'number'), field('expansion_slots', 'تعداد شکاف توسعه', 'Expansion slots', 'number'), field('max_cooler_height_mm', 'حداکثر ارتفاع خنک‌کننده (میلی‌متر)', 'Maximum cooler height (mm)', 'number'), field('drive_bays', 'جایگاه‌های ذخیره‌سازی و تعداد', 'Drive bays and counts', 'counts')],
  psu: [field('wattage_w', 'توان نامی (وات)', 'Rated power (W)', 'number'), form, length, field('connectors', 'کانکتورها و تعداد', 'Connectors and counts', 'counts')],
  cooler: [{ ...field('cooling_type', 'نوع خنک‌کننده', 'Cooling type'), options: ['air', 'liquid'] }, field('sockets', 'سوکت‌های پشتیبانی‌شده', 'Supported sockets', 'list'), height, field('max_memory_height_mm', 'حداکثر ارتفاع رم (میلی‌متر)', 'Maximum memory height (mm)', 'number'), field('approved_cpu_models', 'مدل‌های پردازندهٔ تأییدشده', 'Approved CPU models', 'list')],
  gpu: [length, height, field('slots', 'تعداد اسلات اشغال‌شده', 'Slots occupied', 'number'), field('board_power_w', 'توان برد (وات)', 'Board power (W)', 'number'), field('recommended_psu_w', 'منبع تغذیهٔ پیشنهادی (وات)', 'Recommended PSU (W)', 'number'), field('power_connectors', 'کانکتورهای برق و تعداد', 'Power connectors and counts', 'counts'), field('vram_gb', 'حافظهٔ گرافیکی (گیگابایت)', 'Video memory (GB)', 'number')],
  peripheral: [{ ...field('role', 'نوع وسیله', 'Peripheral role'), required: true, options: ['monitor', 'keyboard', 'mouse', 'audio', 'chair', 'desk', 'accessory'] }, field('connection', 'نوع اتصال', 'Connection')],
  prebuilt: [field('cpu_model', 'مدل پردازنده', 'CPU model'), field('gpu_model', 'مدل کارت گرافیک', 'GPU model'), field('memory_gb', 'حافظه (گیگابایت)', 'Memory (GB)', 'number'), field('storage_gb', 'ذخیره‌سازی (گیگابایت)', 'Storage (GB)', 'number'), field('component_descriptions', 'توضیحات قطعات', 'Component descriptions', 'list')],
};

/** Parse decimal text exactly: UI tomans -> rials, UI dollars -> cents. No FX. */
export function parseMarketAmount(input: string, market: 'ir' | 'international'): number | null {
  const value = input.trim().replace(/[۰-۹]/g, digit => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit))).replace(/[٠-٩]/g, digit => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit))).replace('٫', '.');
  if (!(market === 'ir' ? /^\d{1,13}$/ : /^\d{1,13}(\.\d{1,2})?$/).test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  const amount = market === 'ir' ? BigInt(whole) * BigInt(10) : BigInt(whole) * BigInt(100) + BigInt(fraction.padEnd(2, '0'));
  return amount > BigInt(0) && amount <= BigInt(9_000_000_000_000) ? Number(amount) : null;
}
export function marketAmountInput(amount: number, market: 'ir' | 'international'): string {
  return market === 'ir' ? String(amount / 10) : `${Math.floor(amount / 100)}.${String(amount % 100).padStart(2, '0')}`;
}
