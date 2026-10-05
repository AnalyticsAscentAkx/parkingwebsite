/* Alert signup.
 *
 * Posts to a small separate Worker; the site itself has no backend. If that
 * Worker is unreachable the form says so rather than showing a thank-you it
 * has not earned. A signup form that silently discards addresses is worse
 * than no form, because nobody ever finds out.
 */
(function () {
  "use strict";

  /* Set this to the URL wrangler prints after `npx wrangler deploy`, or to
     https://alerts.parkingnetherlands.com once the custom domain is routed.
     See workers/subscribe/README.md. */
  var ENDPOINT = "https://alerts.parkingnetherlands.com";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var forms = document.querySelectorAll("form[data-subscribe]");
    Array.prototype.forEach.call(forms, function (form) {
      var email = form.querySelector('input[type="email"]');
      var consent = form.querySelector('input[name="consent"]');
      var btn = form.querySelector('button[type="submit"]');
      var note = form.querySelector("[data-note]");
      var pot = form.querySelector('input[name="website"]');

      function say(msg, kind) {
        if (!note) return;
        note.textContent = msg;
        note.dataset.kind = kind;
      }

      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var addr = (email && email.value || "").trim();
        if (addr.indexOf("@") < 1 || addr.indexOf(".", addr.indexOf("@")) < 0) {
          say("That does not look like an email address.", "bad");
          if (email) email.focus();
          return;
        }
        if (consent && !consent.checked) {
          say("Please tick the box so we have your permission to write to you.", "bad");
          return;
        }

        var topics = Array.prototype.map.call(
          form.querySelectorAll('input[name="topic"]:checked'),
          function (i) { return i.value; });

        if (btn) { btn.disabled = true; btn.dataset.was = btn.textContent; btn.textContent = "Sending"; }
        say("", "");

        fetch(ENDPOINT + "/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: addr,
            topics: topics,
            consent: true,
            source: location.pathname,
            website: pot ? pot.value : "",
          }),
        })
          .then(function (r) { return r.json().catch(function () { return {}; }); })
          .then(function (d) {
            if (d && d.ok) {
              form.innerHTML =
                '<p class="sub-done"><b>' +
                (d.already ? "You were already on the list." : "You are on the list.") +
                "</b> Nothing will arrive until there is something worth sending, and " +
                "every email will have an unsubscribe link in it.</p>";
              if (window.gtag) window.gtag("event", "subscribe");
              return;
            }
            var why = d && d.error;
            say(why === "bad_email" ? "That address was rejected. Check it for a typo."
              : why === "rate_limited" ? "Too many attempts from this connection. Try again later."
              : "Something went wrong at our end and your address was not saved. "
                + "Please try again, or email us and we will add you by hand.", "bad");
          })
          .catch(function () {
            say("We could not reach the signup service, so your address was not saved. "
              + "Please try again in a moment.", "bad");
          })
          .then(function () {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.was || "Subscribe"; }
          });
      });
    });
  });
})();
