function t1_flip(frames, screenNumber)
% T1 -- flip timing, Psychtoolbox arm. Mirrors t1_flip.py.
%
%   t1_flip(3000)

    if nargin < 1, frames = 3000; end
    if nargin < 2, screenNumber = max(Screen('Screens')); end

    Screen('Preference', 'SkipSyncTests', 0);   % sync tests ON: this IS the test
    [w, rect] = Screen('OpenWindow', screenNumber, 0);
    cleanup = onCleanup(@() sca);

    Priority(MaxPriority(w));                   % PTB's equivalent of core.rush
    patch = CenterRect([0 0 200 200], rect);

    for i = 1:10, Screen('Flip', w); end        % warm-up, discarded

    t = zeros(frames, 1);
    for i = 1:frames
        if mod(i, 2) == 0
            Screen('FillRect', w, 255, patch);
        end
        t(i) = Screen('Flip', w);
    end
    Priority(0);

    iv = diff(t) * 1000;
    refresh = median(iv);
    dropped = sum(iv > refresh * 1.5);

    fprintf('T1  inter-flip interval (ms), frames=%d\n', frames);
    printStats(iv);
    fprintf('  implied refresh: %.2f Hz\n', 1000/refresh);
    fprintf('  dropped frames : %d / %d  (%.3f%%)\n', dropped, numel(iv), ...
        100*dropped/numel(iv));

    saveResult('t1_flip_matlab', iv, struct('frames', frames, ...
        'dropped', dropped, 'refresh_hz', 1000/refresh));
end
