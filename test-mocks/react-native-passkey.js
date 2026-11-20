module.exports = {
  Passkey: {
    create: jest.fn(),
    get: jest.fn(),
    isSupported: jest.fn(() => true),
  },
};
