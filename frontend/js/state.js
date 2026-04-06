/* ═══════════════════════════════════════════
   STATE
═══════════════════════════════════════════ */
const state = {
  user: null,
  schedules: [],
  bookings: [],
  stats: null,
  schedule: null,
  selectedDate: null,
  selectedTime: null,
  selectedSlotUtc: null,
  selectedTimeLocal: null,
  monthSlots: {},
  currentMonth: new Date(),
  screenStack: [],
  currentScreen: 's-home',
  pendingCancelId: null,
  pendingDeleteId: null,
  isGuestMode: false,
  scheduleId: null,
};

