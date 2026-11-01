// The plain-English words around the numbers: each page's opening tip, the
// "Words explained" definitions, and what each risk area asks.
//
// Written by Emma for the Streamlit app (mystocks_frontend-/app/theme.py and
// app/views/*.py), worded from the backend's own descriptions in core/, and
// carried over word for word. To add or edit a definition, change it here only.
// **double stars** make a word bold.

export const GLOSSARY: Record<string, string> = {
  Gain: 'How much more (or less) your stocks are worth now than what you paid for them.',
  '% of portfolio': 'The slice of your total money that is in this one stock.',
  'S&P 500 twin': "An imaginary copy of your portfolio that put the same money into the S&P 500 (the SPY fund) on the same days. If you're ahead of your twin, you beat the market.",
  Diversification: 'Spreading your money across different stocks and industries, so one bad stock hurts less.',
  'Risk score': "0 to 100 from eight checks on how your portfolio could get hurt. Higher means bumpier. A low score doesn't mean no risk: every stock can still fall.",
  Beta: 'How much you tend to move when the S&P 500 moves. Beta 1.2 means a 10% market fall has tended to mean about 12% for you.',
  Correlation: "Whether two stocks rise and fall together. 1 means always together, 0 means unrelated. If your stocks move together, owning several protects you less than you'd think.",
  'Worst drop': 'The biggest fall from a peak to a low. -25% means that at its worst, $10,000 shrank to $7,500.',
  'Bad day (1 in 20)': 'On a bad day, the kind that happens about 1 day in 20, how much you could lose.',
  'Score (0 to 100)': 'Each stock is checked six ways (business health, rivals, value, economy, price chart, analysts). 50 is neutral; higher is better.',
  Momentum: "Whether a stock (and the experts' opinions of it) have been moving up or down lately.",
  RSI: 'A 0 to 100 gauge of how fast a price has moved. Above 70 means it ran up fast and may cool off. Below 30 means it fell fast and may bounce.',
  'Moving average': 'The average closing price over the last 50 or 200 days. It smooths out daily noise so you can see the trend.',
  DCF: "A way to estimate what a business is worth: add up the cash it may hand back in future, shrunk down because future money is worth less than money today. It's only as good as its guesses.",
  'P/E': 'Price divided by yearly profit per share: how many dollars you pay for each $1 of profit. Lower is cheaper.',
  'Sharpe ratio': 'Return for each bump of risk. Above 1 is good, above 2 is excellent.',
  'Yearly swings': 'How much the value bounces around in a year. Bigger means bumpier.',
  'FOMO (chasing)': "Buying because a price has been rising fast and you don't want to miss out. Prices that run up quickly often cool off.",
  'Averaging down': "Buying more of a stock you're losing money on, hoping to get back to even faster.",
  'Panic selling': 'Selling in a hurry right after a sharp drop, which often locks in the worst price.',
  'Superficial loss': 'In Canada, buying back a stock within 30 days of selling it at a loss can stop you claiming that loss for tax. Not tax advice: check with an accountant.',
  Overtrading: 'Lots of trades in a short time. Every trade costs fees and attention, and busy traders usually do worse.',
}

// One plain question per risk area (from the backend's own descriptions).
export const AREA_HELP: Record<string, string> = {
  Concentration: 'Too many eggs in one basket? Looks at your biggest holding and how few stocks you really depend on.',
  Sector: 'Is too much of your money in one industry?',
  Currency: 'How much is in a foreign currency, and what a 10% move in the exchange rate would do to your total.',
  'Moving together': "Do your stocks rise and fall together? If so, owning several protects you less than you'd think.",
  'Who brings risk': 'Each stock’s share of your money next to its share of your ups and downs. A small holding can bring big swings.',
  'Market risk': 'How much you tend to move when the S&P 500 moves.',
  'Worst drop': 'The biggest fall from a peak over the past few years.',
  'Bad day': 'On a bad day, the kind that happens about 1 day in 20, how much you could lose.',
}

// Each page's one-line "what this means" tip, and the words it explains at the bottom.
// The keys are the React pages; the Streamlit tab each came from is noted.
export const PAGES: Record<string, { tip: string; terms: string[] }> = {
  Setup: {   // Streamlit start page
    tip: "Stocks can feel like a bet. This app helps you **understand** what you hold and why: plain-English scores, the risks to watch, and the common traps to avoid. It explains, it doesn't tell you what to buy.",
    terms: [],
  },
  Dashboard: {   // Overview tab
    tip: "Here's everything you own in one place. **Today** is the move since yesterday's close. **Since you bought** compares what it's worth now with what you paid.",
    terms: ['Gain', '% of portfolio', 'S&P 500 twin', 'Diversification'],
  },
  MyStocks: {   // Overview tab
    tip: "Here's everything you own in one place. **Today** is the move since yesterday's close. **Since you bought** compares what it's worth now with what you paid.",
    terms: ['Gain', '% of portfolio', 'S&P 500 twin', 'Diversification'],
  },
  MyAnalysis: {   // Stocks tab
    tip: "Each stock gets a **0 to 100 score** from six checks: business health, rivals, value, the economy, the price chart and what analysts say. It's a rule of thumb for deciding **what to look into**, not what to buy or sell.",
    terms: ['Score (0 to 100)', 'Momentum', 'RSI', 'Moving average', 'DCF', 'P/E'],
  },
  MyRisks: {   // Risk tab
    tip: 'Risk is about **how much your portfolio could drop**, not whether it will. We check eight areas, score them 0 to 100 (lower = calmer), and show what stands out. It uses the past few years of prices, which is a guide, not a promise.',
    terms: ['Risk score', 'Diversification', 'Correlation', 'Beta', 'Worst drop', 'Bad day (1 in 20)'],
  },
  MyOptimizer: {   // Improve tab
    tip: 'Set your own rules below. We try thousands of different splits of **the stocks you already own** on their past prices, throw out any that break your rules, and show the best one next to what you have now. The best mix for the past is rarely the best for the future, so use it as a starting point.',
    terms: ['Sharpe ratio', 'Yearly swings', 'Worst drop', 'Diversification'],
  },
  MyEdit: {   // Improve tab, "Tweak it yourself"
    tip: "Set one stock to the % you like. The others share what's left in the same proportions. We'll tell you which of your rules that breaks.",
    terms: ['Sharpe ratio', 'Yearly swings', 'Worst drop', 'Diversification'],
  },
  'Decision / Action': {   // new page with no Streamlit match: written for the React app
    tip: 'Pick the mix you want to move toward. Nothing is bought or sold here: you record each real trade in the warning check, after checking it for traps.',
    terms: ['Diversification'],
  },
  'Warning Check': {   // Alerts tab
    tip: "These are **common investing traps** (like buying because everyone else is, or selling in a panic). We point them out so you can pause and think. We never block anything: it's your call.",
    terms: ['FOMO (chasing)', 'Averaging down', 'Panic selling', 'Superficial loss', 'Overtrading'],
  },
}

// The help under each optimizer rule (Improve tab).
export const RULE_HELP: Record<string, string> = {
  goal: 'Highest Sharpe ratio = the most return for each bump of risk. Lowest risk = the calmest mix. Highest return = the biggest past growth.',
  max_weight_pct: "Stops the best mix from piling everything into last period's winner.",
  min_weight_pct: '0 lets it drop a stock completely.',
  max_drawdown_pct: 'The biggest drop from a peak you can stomach. 25 means $10,000 shrinking to $7,500 at its worst.',
  min_return_pct: "The least you'd accept per year, on average, in the past data.",
}

// The five tabs under a stock's verdict (Stocks tab, "Look closer"): name and one-line caption.
export const STOCK_TABS: [string, string, string][] = [
  ['technicals', 'Technicals', 'What the price chart is doing: trend, moving averages and RSI. Often wrong over short periods.'],
  ['analysts', 'Analysts', 'What professional analysts say, and which way their opinions are moving. Analysts lean optimistic.'],
  ['dcf', 'Valuation (DCF)', 'A DCF is very sensitive to its assumptions. Treat the result as one input, not an answer.'],
  ['ratios', 'Financials', "The standard health numbers from the company's reports. 'n/a' means the company doesn't report it."],
  ['rivals', 'Rivals', 'How it stacks up against its biggest competitors, scored 0 to 100.'],
]

export const TRADE_HELP = "Tell us what you're about to do and, if you like, why. Writing the reason down is a good habit."

export const DISCLAIMER = 'A rule of thumb based on past data, not financial advice.'
