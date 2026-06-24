on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theSubtitle to item 3 of argv
    set theSoundName to item 4 of argv

    if theSubtitle is "" and theSoundName is "" then
        display notification theMessage with title theTitle
    else if theSubtitle is "" then
        display notification theMessage with title theTitle sound name theSoundName
    else if theSoundName is "" then
        display notification theMessage with title theTitle subtitle theSubtitle
    else
        display notification theMessage with title theTitle subtitle theSubtitle sound name theSoundName
    end if
end run
