# DutchReview submission: ready to paste

The form wants a finished article at a shareable link, not a pitch. Everything
below is written. Paste the article into a Google Doc, set sharing to "anyone
with the link can view", and put that link in the form.

Only three things are yours: your name, your email, and the author photo.

**Fix this first.** The homepage says the median public charging price is €0.37
per kWh. The EV charging page says €0.41, with a range of €0.28 to €0.63 and a
national average of €0.43. Both are live right now. The article uses €0.41,
because that page states its range and average and reads as the sourced one, but
the two pages must agree before a journalist checks them. That is exactly the
sort of thing that gets spotted.

---

## Field 1: Your name

Yours.

## Field 2: Your email

The Analytics Ascent address, not the enviolo one.

## Field 3: Pitch a headline

> I kept being surprised by my charging bill, so I worked out what is actually
> going on: you are paying for parking too

Alternative, if they prefer a number in the headline:

> Nobody tells you this: parking is up to 47% of the cost of charging your car

## Field 4: What's your article about?

> I drive an EV and I kept getting charging bills that did not match what the
> app quoted. It turned out the electricity was only part of it. A charging bay
> inside a paid parking zone is still a paid parking space, so the hourly tariff
> runs on top, and nothing tells you that at the moment you plug in.
>
> So I started tracking it, then I built a free tool that prices both halves
> together, and now anyone can use it.
>
> The findings: across 14 Dutch cities, parking is between 27% and 47% of the
> total cost of a typical two hour, 20 kWh stop. In Delft it is almost half. On
> top of that the electricity itself ranges from €0.28 to €0.63 per kWh
> depending purely on which operator owns the post. At least 12,667 Dutch charge
> points sit inside a paid parking area.
>
> About 950 words, personal, with the city table and practical advice. All
> figures come from the national charging register and the national parking
> register, and the tool is free with no sign-up.

## Field 5: Link to your article

Paste the article below into a Google Doc. Set sharing to "anyone with the link".
Put that link here.

## Field 6: Author bio

> [Your name] drives an electric car in the Netherlands and got tired of being
> surprised by the bill, so he started compiling the national charging register
> and the national parking register into one place. The result is
> parkingnetherlands.com, which is free, has no sign-up, and exists mainly
> because he wanted to stop overpaying by accident.

Adjust the pronoun. DutchReview explicitly ask for personality, so keep it human.

## Field 7: Author image

Yours. Any clear headshot.

---

# THE ARTICLE

## I kept being surprised by my charging bill, so I worked out what is actually going on

The first time it happened I assumed I had misread something.

I plugged in somewhere in central Amsterdam, went off for a couple of hours, came
back, and the total was noticeably more than the kWh price had led me to expect.
Not catastrophically more. Just enough to be irritating, and just vague enough
that I could not be bothered to work out why.

The second time, I worked out why.

### The bit nobody mentions

A charging bay inside a paid parking zone is still a paid parking space.

That is it. That is the whole trick. The electricity is metered and priced and
shown to you in the app. The ground the car is standing on while it charges is
also being charged for, at the normal municipal hourly tariff, and absolutely
nothing at the charge point tells you that.

I started keeping track, mostly out of spite. Then it became a spreadsheet. Then
the spreadsheet became unmanageable, because the Netherlands has 196,151 public
charge points and the parking tariffs sit in separate municipal decisions, one
per city, published as PDFs that were plainly never meant to be compared.

So I built the thing I wanted to exist, and put it online for free.

### What the numbers say

Here is a normal stop: 20 kWh of electricity over two hours, which is roughly
topping up a mid-size EV while you do something else.

Electricity at the national median of €0.41 per kWh comes to €8.20, wherever you
are. The parking is what changes.

| City | Parking, 2 hours | Total | Parking's share |
|---|---|---|---|
| Delft | €7.28 | €15.48 | 47% |
| Utrecht | €7.16 | €15.36 | 47% |
| Haarlem | €6.98 | €15.18 | 46% |
| The Hague | €6.40 | €14.60 | 44% |
| Amsterdam | €6.00 | €14.20 | 42% |
| Nijmegen | €5.80 | €14.00 | 41% |
| Zwolle | €5.46 | €13.66 | 40% |
| Groningen | €4.50 | €12.70 | 35% |
| Maastricht | €4.34 | €12.54 | 35% |
| Rotterdam | €4.00 | €12.20 | 33% |
| Breda | €4.00 | €12.20 | 33% |
| Tilburg | €4.00 | €12.20 | 33% |
| Leiden | €3.80 | €12.00 | 32% |
| Eindhoven | €3.00 | €11.20 | 27% |

In Delft and Utrecht, almost half of what you pay to charge your car is not
electricity at all. Across these fourteen cities the average is 38%.

At least 12,667 Dutch charge points sit inside a paid parking area. That is not
a loophole anyone is exploiting. It is just two separate systems, each working
exactly as designed, billing you independently and never introducing themselves.

### And then there is the electricity itself

While I was at it I found the other half of the problem.

The median is €0.41 per kWh, but most chargers land anywhere between €0.28 and
€0.63. Same electricity, same grid, same country. The difference is which company
owns the post.

Vattenfall InCharge averages €0.32 per kWh. E-Flux by Road averages €0.51. That
is roughly 60% more for an identical electron, decided by a logo you probably did
not look at.

So you have two hidden variables that multiply: an operator price you cannot see
until you are connected, and a parking tariff nobody mentions at all. A €20 stop
and an €11 stop can look completely identical from the driver's seat.

### What I did about it

I put all of it in one place: every public charge point in the country, its
operator's price, and the parking tariff for the ground underneath it, added
together for the length of stop you actually want.

It is free. There is no sign-up, no app, and no account. I am not selling
anything, which I mention only because it is a reasonable thing to wonder about
a website offering you a free tool.

You can use it here:
[parkingnetherlands.com](https://parkingnetherlands.com)

### Three things worth knowing even if you never use it

**Check whether the bay is in a paid zone before you plug in.** This is the
single biggest avoidable cost, and it takes five seconds.

**The operator matters more than the city.** Driving to a cheaper town saves you
very little. Picking a different post can save you 60% on the electricity.

**For anything over two hours, look at P+R.** The combined maths flips quickly,
and Dutch P+R is deliberately priced to make you use it.

### Check my homework

The charging data comes from the national charge point register via NDW and
DOT-NL. The parking tariffs come from the national parking register, covering 323
register-listed garages across 14 cities, snapshot 30 September 2026.

Both datasets are published openly on the site, and if you find my arithmetic is
wrong I would genuinely like to know, because at this point it is my bill too.
