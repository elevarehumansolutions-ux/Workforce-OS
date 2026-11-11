// When the next scoring quarter begins, worked out from the company's fiscal year start month.
// A quarter is three months: with a fiscal year starting in April, quarters begin on 1 April,
// 1 July, 1 October and 1 January. (Whole days only; the server's nightly job does the exact
// timing in the company's timezone.)

export interface NextQuarter {
  // Whole days from today until it begins (0 = begins today).
  daysAway: number;
  startsOn: Date;
}

export function nextQuarterStart(fiscalYearStartMonth: number, today: Date): NextQuarter {
  const startMonths: number[] = [];
  for (let i = 0; i < 4; i++) {
    startMonths.push(((fiscalYearStartMonth - 1 + i * 3) % 12) + 1);
  }

  // The first 1st-of-a-quarter-month that is today or later, looking at this year and the next.
  let best: Date | null = null;
  for (let yearOffset = 0; yearOffset <= 1; yearOffset++) {
    for (const month of startMonths) {
      const candidate = new Date(today.getFullYear() + yearOffset, month - 1, 1);
      const sameOrLater = candidate.getTime() >= new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
      if (sameOrLater && (best === null || candidate.getTime() < best.getTime())) {
        best = candidate;
      }
    }
  }
  const startsOn = best as Date;
  const oneDay = 24 * 60 * 60 * 1000;
  const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return { daysAway: Math.round((startsOn.getTime() - todayMidnight.getTime()) / oneDay), startsOn: startsOn };
}
