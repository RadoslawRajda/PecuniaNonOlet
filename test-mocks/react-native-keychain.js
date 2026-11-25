let credentials = null;

module.exports = {
  ACCESSIBLE: {WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'WHEN_UNLOCKED_THIS_DEVICE_ONLY'},
  getGenericPassword: jest.fn(async () => credentials),
  setGenericPassword: jest.fn(async (username, password, options) => {
    credentials = {username, password, service: options?.service};
    return true;
  }),
  resetGenericPassword: jest.fn(async () => {
    credentials = null;
    return true;
  }),
};
