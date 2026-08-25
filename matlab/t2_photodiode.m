function t2_photodiode(cfgName, flips, rate, screenNumber)
% T2 -- photodiode ground truth, Psychtoolbox arm. Mirrors t2_photodiode.py.
%
% WIRING (identical to the Python arm -- do not re-cable between arms):
%   photodiode aimed at stimulus monitor corner -> ai0
%   TTL line 'A' BNC on the breakout box        -> ai1
%
% Both digitised by the same PCIe-6351 clock, so the TTL->photon interval owes
% nothing to either computer's software clock.
%
%   t2_photodiode('rig-right', 300, 50000)

    if nargin < 1, cfgName = 'rig-right'; end
    if nargin < 2, flips   = 300;         end
    if nargin < 3, rate    = 50000;       end
    if nargin < 4, screenNumber = max(Screen('Screens')); end

    cclabInitDIO(cfgName);
    cleanupDIO = onCleanup(@() cclabCloseDIO());

    % Separate DAQ session for capture. cclabInitDIO owns the digital lines;
    % this owns the analog inputs. They do not conflict on an X-series card.
    daqs = daqlist();
    devID = '';
    for i = 1:size(daqs,1)
        if strcmp(daqs(i,:).Model, "PCIe-6351"), devID = daqs(i,:).DeviceID; break; end
    end
    assert(~isempty(devID), 'No PCIe-6351 found.');

    dq = daq("ni");
    dq.Rate = rate;
    addinput(dq, devID, "ai0", "Voltage");   % photodiode
    addinput(dq, devID, "ai1", "Voltage");   % TTL loopback

    Screen('Preference', 'SkipSyncTests', 0);
    [w, rect] = Screen('OpenWindow', screenNumber, 0);
    cleanupScr = onCleanup(@() sca);
    ifi = Screen('GetFlipInterval', w);
    Priority(MaxPriority(w));

    patch = CenterRect([0 0 200 200], rect);
    patch = OffsetRect([0 0 200 200], 10, 10);   % corner, where the diode sits

    for i = 1:10, Screen('Flip', w); end          % warm-up, discarded

    nSamples = round((flips * ifi + 1.0) * rate);
    start(dq, "NumScans", nSamples);

    t = zeros(flips, 1);
    for i = 1:flips
        if mod(i, 2) == 1
            Screen('FillRect', w, 255, patch);
        end
        t(i) = Screen('Flip', w);
        cclabPulse('A', 1.0);
    end

    data = read(dq, "all", "OutputFormat", "Matrix");
    stop(dq);
    Priority(0);

    pd  = data(:,1);
    ttl = data(:,2);
    pdT  = risingEdges(pd,  rate, autoThreshold(pd));
    ttlT = risingEdges(ttl, rate, autoThreshold(ttl));
    lag  = pairEdges(ttlT, pdT, 2*ifi) * 1000;

    dropped = sum(~isfinite(lag));
    fprintf('T2  TTL -> photon (ms), flips=%d\n', flips);
    printStats(lag);
    fprintf('  edges : %d TTL / %d photodiode\n', numel(ttlT), numel(pdT));
    fprintf('  unpaired (dropped?): %d\n', dropped);

    saveResult('t2_photodiode_matlab', lag, struct('flips', flips, ...
        'rate', rate, 'dropped', dropped, 'ifi', ifi, 'cfg', cfgName));
end

function thr = autoThreshold(sig)
% Floor from a low percentile (robust to noise), ceiling from the max.
% NOT a high percentile: a 1ms TTL inside a 16.7ms frame is ~1% duty cycle,
% so even the 99th percentile still sits in the low state.
    lo = prctile(sig, 1);
    hi = max(sig);
    assert(hi - lo >= 0.1, ...
        'Signal has no usable swing (floor=%.3fV peak=%.3fV). Check the photodiode.', lo, hi);
    thr = (lo + hi) / 2;
end

function tEdges = risingEdges(sig, rate, thr)
% Debounced low->high crossings. An LCD ramp can wobble across the threshold
% several times on one true transition; each wobble would otherwise become a
% spurious event and corrupt the pairing.
    high = sig > thr;
    idx  = find(~high(1:end-1) & high(2:end)) + 1;
    if isempty(idx), tEdges = []; return; end
    minGap = round(0.002 * rate);
    keep = idx(1);
    for k = 2:numel(idx)
        if idx(k) - keep(end) >= minGap, keep(end+1) = idx(k); end %#ok<AGROW>
    end
    tEdges = keep(:) / rate;
end

function out = pairEdges(ttlT, pdT, maxLag)
% For each TTL edge, delay to the next photodiode edge within maxLag.
% NaN where none followed -- that is what a dropped frame looks like.
% maxLag must stay below the inter-flip interval, or a dropped frame silently
% pairs with the next frame and reports a lag one refresh too long.
    out = nan(size(ttlT));
    j = 1;
    for i = 1:numel(ttlT)
        while j <= numel(pdT) && pdT(j) < ttlT(i), j = j + 1; end
        if j <= numel(pdT) && pdT(j) - ttlT(i) <= maxLag
            out(i) = pdT(j) - ttlT(i);
        end
    end
end
