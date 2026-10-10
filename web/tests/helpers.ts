let passed = 0;
export const test = (name: string, fn: () => void): void => {
  fn();
  passed++;
  console.log('ok  ', name);
};
export const count = (): number => passed;
