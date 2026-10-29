import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { parseMarketAmount, marketAmountInput, specFields } from '../src/lib/admin-form-fields';

test('market amount input preserves exact minor units and never exchanges markets', () => {
  expect(parseMarketAmount('۱۲۳۴۵۶', 'ir')).toBe(1234560);
  expect(parseMarketAmount('١٢٩٫٩٩', 'international')).toBe(12999);
  expect(parseMarketAmount('0.29', 'international')).toBe(29);
  expect(parseMarketAmount('1.1', 'international')).toBe(110);
  expect(parseMarketAmount('900000000000', 'ir')).toBe(9_000_000_000_000);
  expect(parseMarketAmount('90000000000.00', 'international')).toBe(9_000_000_000_000);
  for (const input of ['', '0', '-1', '1e3', '1,000', 'NaN', 'Infinity', '1.001', '90000000001.00', '99999999999999999999999']) {
    expect(parseMarketAmount(input, 'ir')).toBeNull();
    expect(parseMarketAmount(input, 'international')).toBeNull();
  }
  expect(parseMarketAmount('12.50', 'ir')).toBeNull();
  expect(parseMarketAmount('900000000001', 'ir')).toBeNull();
  for (const amount of [1, 29, 999, 9000000000000]) expect(parseMarketAmount(marketAmountInput(amount, 'international'), 'international')).toBe(amount);
  expect(marketAmountInput(1234560, 'ir')).toBe('123456');
});

test('technical form covers every contract field without weakening type or required constraints', () => {
  const { components: { schemas } } = JSON.parse(readFileSync('../../contracts/openapi/catalog.json', 'utf8'));
  const kinds = schemas.VariantContent.properties.specifications.discriminator.mapping as Record<string, string>;
  expect(Object.keys(specFields).sort()).toEqual(Object.keys(kinds).sort());
  for (const [kind, reference] of Object.entries(kinds)) {
    const schema = schemas[reference.split('/').at(-1)!];
    const fields = specFields[kind as keyof typeof specFields];
    expect(fields.map(field => field.key).sort()).toEqual(Object.keys(schema.properties).filter(key => key !== 'kind').sort());
    for (const field of fields) {
      const property = schema.properties[field.key];
      const type = property.anyOf?.find((option: { type: string }) => option.type !== 'null') || property;
      expect(!!field.required).toBe((schema.required || []).includes(field.key));
      if (type.type === 'integer') expect(field.type).toBe('number');
      if (type.type === 'boolean') expect(field.type).toBe('boolean');
      if (type.type === 'array') expect(field.type).toBe('list');
      if (type.type === 'object') expect(field.type).toBe('counts');
      if (type.enum) expect(field.options).toEqual(type.enum);
    }
  }
});
