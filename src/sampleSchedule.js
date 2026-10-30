// A sample week for the app: the 24 sample nurses, the shifts from the AI's passing draft for the week of
// Nov 2 to 8, 2026, and the sample leave requests (backend/data/mock). Mock data only.
// Day shift 07:00-19:00, night 19:00-07:00. Nobody works two shifts in a day or on approved leave.

export const SAMPLE_WEEK = "Mon, Nov 2 to Sun, Nov 8, 2026";

const NURSES = [
  {
    "id": "N001",
    "name": "Avery Brooks",
    "isAdmin": false
  },
  {
    "id": "N002",
    "name": "Jordan Patel",
    "isAdmin": false
  },
  {
    "id": "N003",
    "name": "Casey Nguyen",
    "isAdmin": false
  },
  {
    "id": "N004",
    "name": "Riley Thompson",
    "isAdmin": false
  },
  {
    "id": "N005",
    "name": "Drew Santos",
    "isAdmin": false
  },
  {
    "id": "N006",
    "name": "Taylor Kim",
    "isAdmin": false
  },
  {
    "id": "N007",
    "name": "Jamie Okafor",
    "isAdmin": false
  },
  {
    "id": "N008",
    "name": "Quinn Rossi",
    "isAdmin": false
  },
  {
    "id": "N009",
    "name": "Dakota Ellis",
    "isAdmin": false
  },
  {
    "id": "N010",
    "name": "Skyler Bennett",
    "isAdmin": false
  },
  {
    "id": "N011",
    "name": "Reese Alvarez",
    "isAdmin": false
  },
  {
    "id": "N012",
    "name": "Parker Singh",
    "isAdmin": false
  },
  {
    "id": "N013",
    "name": "Emerson Cole",
    "isAdmin": false
  },
  {
    "id": "N014",
    "name": "Rowan Fischer",
    "isAdmin": false
  },
  {
    "id": "N015",
    "name": "Harper Lewis",
    "isAdmin": false
  },
  {
    "id": "N016",
    "name": "Sage Mitchell",
    "isAdmin": false
  },
  {
    "id": "N017",
    "name": "Morgan Reyes",
    "isAdmin": false
  },
  {
    "id": "N018",
    "name": "Finley Grant",
    "isAdmin": false
  },
  {
    "id": "N019",
    "name": "Logan Hayes",
    "isAdmin": false
  },
  {
    "id": "N020",
    "name": "Blake Moreno",
    "isAdmin": false
  },
  {
    "id": "N021",
    "name": "Cameron Doyle",
    "isAdmin": false
  },
  {
    "id": "N022",
    "name": "Sasha Whitfield",
    "isAdmin": false
  },
  {
    "id": "N023",
    "name": "Devon Park",
    "isAdmin": false
  },
  {
    "id": "N024",
    "name": "Kai Lindqvist",
    "isAdmin": false
  }
];

const SHIFTS = [{"id":"sample-N008-2026-11-02-day","employeeId":"N008","date":"2026-11-02","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N016-2026-11-02-day","employeeId":"N016","date":"2026-11-02","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N020-2026-11-02-day","employeeId":"N020","date":"2026-11-02","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N022-2026-11-02-day","employeeId":"N022","date":"2026-11-02","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N024-2026-11-02-day","employeeId":"N024","date":"2026-11-02","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N002-2026-11-02-night","employeeId":"N002","date":"2026-11-02","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N013-2026-11-02-night","employeeId":"N013","date":"2026-11-02","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N021-2026-11-02-night","employeeId":"N021","date":"2026-11-02","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N023-2026-11-02-night","employeeId":"N023","date":"2026-11-02","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N007-2026-11-03-day","employeeId":"N007","date":"2026-11-03","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N010-2026-11-03-day","employeeId":"N010","date":"2026-11-03","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N011-2026-11-03-day","employeeId":"N011","date":"2026-11-03","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N014-2026-11-03-day","employeeId":"N014","date":"2026-11-03","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N018-2026-11-03-day","employeeId":"N018","date":"2026-11-03","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N004-2026-11-03-night","employeeId":"N004","date":"2026-11-03","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N009-2026-11-03-night","employeeId":"N009","date":"2026-11-03","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N017-2026-11-03-night","employeeId":"N017","date":"2026-11-03","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N019-2026-11-03-night","employeeId":"N019","date":"2026-11-03","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N001-2026-11-04-day","employeeId":"N001","date":"2026-11-04","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N005-2026-11-04-day","employeeId":"N005","date":"2026-11-04","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N006-2026-11-04-day","employeeId":"N006","date":"2026-11-04","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N012-2026-11-04-day","employeeId":"N012","date":"2026-11-04","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N015-2026-11-04-day","employeeId":"N015","date":"2026-11-04","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N008-2026-11-04-night","employeeId":"N008","date":"2026-11-04","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N017-2026-11-04-night","employeeId":"N017","date":"2026-11-04","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N018-2026-11-04-night","employeeId":"N018","date":"2026-11-04","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N020-2026-11-04-night","employeeId":"N020","date":"2026-11-04","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N003-2026-11-05-day","employeeId":"N003","date":"2026-11-05","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N011-2026-11-05-day","employeeId":"N011","date":"2026-11-05","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N015-2026-11-05-day","employeeId":"N015","date":"2026-11-05","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N019-2026-11-05-day","employeeId":"N019","date":"2026-11-05","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N022-2026-11-05-day","employeeId":"N022","date":"2026-11-05","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N001-2026-11-05-night","employeeId":"N001","date":"2026-11-05","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N012-2026-11-05-night","employeeId":"N012","date":"2026-11-05","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N013-2026-11-05-night","employeeId":"N013","date":"2026-11-05","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N023-2026-11-05-night","employeeId":"N023","date":"2026-11-05","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N002-2026-11-06-day","employeeId":"N002","date":"2026-11-06","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N010-2026-11-06-day","employeeId":"N010","date":"2026-11-06","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N016-2026-11-06-day","employeeId":"N016","date":"2026-11-06","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N021-2026-11-06-day","employeeId":"N021","date":"2026-11-06","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N024-2026-11-06-day","employeeId":"N024","date":"2026-11-06","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N004-2026-11-06-night","employeeId":"N004","date":"2026-11-06","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N005-2026-11-06-night","employeeId":"N005","date":"2026-11-06","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N006-2026-11-06-night","employeeId":"N006","date":"2026-11-06","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N007-2026-11-06-night","employeeId":"N007","date":"2026-11-06","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N014-2026-11-06-night","employeeId":"N014","date":"2026-11-06","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N003-2026-11-07-day","employeeId":"N003","date":"2026-11-07","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N009-2026-11-07-day","employeeId":"N009","date":"2026-11-07","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N022-2026-11-07-day","employeeId":"N022","date":"2026-11-07","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N024-2026-11-07-day","employeeId":"N024","date":"2026-11-07","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N001-2026-11-07-night","employeeId":"N001","date":"2026-11-07","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N010-2026-11-07-night","employeeId":"N010","date":"2026-11-07","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N011-2026-11-07-night","employeeId":"N011","date":"2026-11-07","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N017-2026-11-07-night","employeeId":"N017","date":"2026-11-07","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N006-2026-11-08-day","employeeId":"N006","date":"2026-11-08","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N012-2026-11-08-day","employeeId":"N012","date":"2026-11-08","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N015-2026-11-08-day","employeeId":"N015","date":"2026-11-08","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N016-2026-11-08-day","employeeId":"N016","date":"2026-11-08","start":"07:00","end":"19:00","status":"scheduled"},{"id":"sample-N007-2026-11-08-night","employeeId":"N007","date":"2026-11-08","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N019-2026-11-08-night","employeeId":"N019","date":"2026-11-08","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N021-2026-11-08-night","employeeId":"N021","date":"2026-11-08","start":"19:00","end":"07:00","status":"scheduled"},{"id":"sample-N023-2026-11-08-night","employeeId":"N023","date":"2026-11-08","start":"19:00","end":"07:00","status":"scheduled"}];

const AVAILABILITY = {
  "N002": {
    "2026-11-07": {
      "status": "unavailable",
      "reason": "Appointment",
      "note": ""
    }
  },
  "N007": {
    "2026-11-02": {
      "status": "unavailable",
      "reason": "Family emergency",
      "note": ""
    }
  },
  "N013": {
    "2026-11-08": {
      "status": "unavailable",
      "reason": "Appointment",
      "note": ""
    }
  },
  "N018": {
    "2026-11-05": {
      "status": "unavailable",
      "reason": "Sick",
      "note": ""
    }
  }
};

const LEAVE = [
  {
    "id": "l01",
    "employeeId": "N003",
    "type": "pto",
    "start": "2026-11-04",
    "end": "2026-11-04",
    "note": "",
    "status": "approved",
    "createdAt": 1793000000000
  },
  {
    "id": "l02",
    "employeeId": "N009",
    "type": "pto",
    "start": "2026-11-06",
    "end": "2026-11-06",
    "note": "Family event",
    "status": "approved",
    "createdAt": 1793100000000
  },
  {
    "id": "l03",
    "employeeId": "N015",
    "type": "vacation",
    "start": "2026-11-02",
    "end": "2026-11-03",
    "note": "Short trip",
    "status": "approved",
    "createdAt": 1793200000000
  },
  {
    "id": "l04",
    "employeeId": "N020",
    "type": "pto",
    "start": "2026-11-07",
    "end": "2026-11-08",
    "note": "",
    "status": "approved",
    "createdAt": 1793300000000
  },
  {
    "id": "l05",
    "employeeId": "N006",
    "type": "pto",
    "start": "2026-11-05",
    "end": "2026-11-05",
    "note": "",
    "status": "approved",
    "createdAt": 1793400000000
  },
  {
    "id": "l06",
    "employeeId": "N012",
    "type": "fmla",
    "start": "2026-11-09",
    "end": "2026-11-15",
    "note": "Request only, paperwork pending",
    "status": "pending",
    "createdAt": 1793500000000
  },
  {
    "id": "l07",
    "employeeId": "N010",
    "type": "overtime",
    "start": "2026-11-08",
    "end": "2026-11-08",
    "note": "Can cover up to 8 extra hours",
    "status": "pending",
    "createdAt": 1793600000000
  },
  {
    "id": "l08",
    "employeeId": "N004",
    "type": "dayoff",
    "start": "2026-11-10",
    "end": "2026-11-10",
    "note": "Appointment",
    "status": "pending",
    "createdAt": 1793300000000
  },
  {
    "id": "l09",
    "employeeId": "N011",
    "type": "dayoff",
    "start": "2026-11-09",
    "end": "2026-11-09",
    "note": "",
    "status": "denied",
    "createdAt": 1793400000000
  }
];

/** A fresh copy of the app's data shape, so loading it twice never shares objects. */
export function sampleData() {
  return structuredClone({
    roster: [{ id: "admin-1", name: "Acting Supervisor", isAdmin: true }, ...NURSES],
    availability: AVAILABILITY,
    shifts: SHIFTS,
    swaps: [],
    leave: LEAVE,
    notifications: [],
  });
}
