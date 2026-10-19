const $ = (id) => document.getElementById(id);

function setStatus(kind, text) {
  const el = $("status");
  el.className = "status " + kind;
  el.textContent = text;
}

async function checkHealth() {
  const el = $("health");
  try {
    const r = await fetch("/health");
    const j = await r.json();
    el.textContent = j.status === "ok" ? "API online" : JSON.stringify(j);
    el.className = "pill " + (j.status === "ok" ? "ok" : "bad");
  } catch (e) {
    el.textContent = "API offline";
    el.className = "pill bad";
  }
}

$("mode").addEventListener("change", () => {
  $("forecastRow").style.display = $("mode").value === "forecast" ? "grid" : "none";
});

$("btnHealth").addEventListener("click", checkHealth);

$("btnRun").addEventListener("click", async () => {
  const mode = $("mode").value;
  const body = {
    mode,
    country: $("country").value.trim() || null,
    adm1: (function(){
      const sel = $("adm1");
      if (sel.multiple) {
        const opts = Array.from(sel.selectedOptions).map(o => o.value.trim()).filter(Boolean);
        return opts.length ? opts.join(",") : null;
      }
      return sel.value.trim() || null;
    })(),
    adm2: $("adm2").value.trim() || null,
    adm3: $("adm3").value.trim() || null,
    start_date: $("start").value,
    end_date: $("end").value,
    forecast_days: Number($("forecastDays").value) || 5,
  };
  const raw = $("aoiJson").value.trim();
  if (raw) {
    try {
      body.aoi_geojson = JSON.parse(raw);
    } catch (e) {
      setStatus("err", "Invalid AOI GeoJSON");
      $("output").textContent = String(e);
      return;
    }
  }

  $("btnRun").disabled = true;
  setStatus("running", "Running… this can take a few minutes (remote streams).");
  $("output").textContent = "Request sent…\n" + JSON.stringify(body, null, 2);

  try {
    const r = await fetch("/v1/ui/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await r.text();
    let j;
    try { j = JSON.parse(text); } catch { j = { raw: text }; }
    if (!r.ok) {
      setStatus("err", "Error " + r.status);
      $("output").textContent = JSON.stringify(j, null, 2);
    } else {
      setStatus("ok", "Completed");
      $("output").textContent = JSON.stringify(j, null, 2);
    }
  } catch (e) {
    setStatus("err", "Request failed");
    $("output").textContent = String(e);
  } finally {
    $("btnRun").disabled = false;
  }
});

checkHealth();

$("btnReport").addEventListener("click", async () => {
  try {
    const r = await fetch("/v1/ui/latest-report");
    const j = await r.json();
    setStatus(j.ok ? "ok" : "err", j.ok ? "Report found" : "No report");
    $("output").textContent = JSON.stringify(j, null, 2);
  } catch (e) {
    setStatus("err", "Report lookup failed");
    $("output").textContent = String(e);
  }
});
