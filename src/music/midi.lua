changeInPercent = 20 -- <== Set this if you don't like 20% increase or decrease

-- Get the selected MIDI notes
local midiEditor = reaper.MIDIEditor_GetActive()
local take = reaper.MIDIEditor_GetTake(midiEditor)
local noteCount = reaper.MIDI_CountEvts(take)

-- Loop through the selected notes
for k = 0, noteCount do
retval, selected, muted, startppqpos, origEnd, chan, pitch, vel = reaper.MIDI_GetNote(take, k)
if selected == true then

-- Get note change +- 20%
randomFactor = (100 + math.random(-changeInPercent, changeInPercent)) / 100.0
origLength = origEnd - startppqpos
newEnd = startppqpos + (origLength * randomFactor)


-- Set the new note length
reaper.MIDI_SetNote(take, k, selected, muted, startppqpos, newEnd, chan, pitch, vel, true)
end
end

-- Update the MIDI editor
reaper.MIDI_Sort(take)
