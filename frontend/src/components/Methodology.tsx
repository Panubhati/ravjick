export function Methodology() {
  return (
    <details className="methodology">
      <summary>Methodology</summary>
      <dl>
        <dt>Cutoff rule</dt>
        <dd>
          Electricity for a day is bought the day before, at a set decision time. The wind forecast
          is updated several times a day, so we show the latest forecast that was out by your
          decision time. Later forecasts are never used, because you could not have seen them. If no
          forecast was out for an hour, that hour is marked as missing and left blank. We never fill
          it in.
        </dd>
        <dt>Hourly alignment</dt>
        <dd>
          The forecast gives one figure per hour; actual wind is measured every half hour. For each
          hour we average the two half-hour measurements. If either is missing, that hour is left out
          of the accuracy figures.
        </dd>
        <dt>Sign convention</dt>
        <dd>
          We work out forecast minus actual. Above zero means less wind came than forecast, so you
          were <strong>short</strong> and had to buy extra. Below zero means more wind came than
          forecast, so you had bought too much.{" "}
          <span className="term">(Technical: error = forecast − actual.)</span>
        </dd>
        <dt>Shortfall buffer (90%)</dt>
        <dd>
          In 9 hours out of 10, actual wind was no more than this far below the forecast. Buying this
          much extra would have covered you in those hours. It is worked out after the fact from all
          January hours, including days after the one you are planning, so treat it as a guide, not
          a guarantee. With only one month of data it is uncertain. The ranges on the Forecast
          Performance tab show by how much.
        </dd>
        <dt>Times and where the data comes from</dt>
        <dd>
          All times are UK time, which is the same as UTC in January. The data comes from Elexon,
          which publishes Great Britain's electricity market data. It covers national wind power,
          for days 1 to 31 January 2026. It is historical and is not updated live.{" "}
          <span className="term">(Technical: Elexon BMRS datasets FUELHH and WINDFOR.)</span>
        </dd>
        <dt>Good to know: the forecast tends to run high</dt>
        <dd>
          In January the forecast was above actual wind in most hours, even when made only a few
          hours ahead. The most likely reason, not yet proven, is that on very windy days the grid
          pays some wind farms to turn down, while the forecast predicts what they could have
          produced. The figures here are the misses a buyer using this forecast really faced. One
          month is a small sample.
        </dd>
      </dl>
    </details>
  );
}
