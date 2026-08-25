function t0_daq(cfgName, n, line, widthMS)
% T0 -- DAQ write latency, MATLAB/Psychtoolbox arm.
%
% Deliberately uses the lab's own cclabPulse unmodified. The point of this arm
% is to measure the stack as it exists today, not a reimplementation of it --
% anything else would be comparing against a strawman.
%
% Requires cclab-matlab-tools and Psychtoolbox on the path.
%
%   t0_daq('rig-right', 10000, 'A', 1.0)
%   t0_daq('dummy', 1000)

    if nargin < 1, cfgName  = 'rig-right'; end
    if nargin < 2, n        = 10000;       end
    if nargin < 3, line     = 'A';         end
    if nargin < 4, widthMS  = 1.0;         end

    cclabInitDIO(cfgName);
    cleanup = onCleanup(@() cclabCloseDIO());   % P13: release hardware on any exit

    for i = 1:20                                % warm-up, discarded
        cclabPulse(line, widthMS);
    end

    elapsed = zeros(n, 1);
    for i = 1:n
        t0 = GetSecs;
        cclabPulse(line, widthMS);
        elapsed(i) = GetSecs - t0;
    end

    % Subtract our own deliberate WaitSecs, leaving driver overhead only.
    overhead = (elapsed - widthMS/1000) * 1000;

    fprintf('T0  DAQ write overhead (ms), n=%d, line=%s, cfg=%s\n', n, line, cfgName);
    printStats(overhead);
    saveResult('t0_daq_matlab', overhead, struct('n', n, 'line', line, ...
        'width_ms', widthMS, 'cfg', cfgName));
end
