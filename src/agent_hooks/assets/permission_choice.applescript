use scripting additions

on run argv
    set theTitle to item 1 of argv
    set thePrompt to item 2 of argv
    set theDefaultLabel to item 3 of argv
    set optionLabels to {}
    repeat with i from 4 to (count of argv)
        set end of optionLabels to item i of argv
    end repeat

    if (count of optionLabels) is 0 then
        return "CANCELLED"
    end if

    set defaultItems to {}
    if theDefaultLabel is not "" then
        repeat with optionLabel in optionLabels
            if (optionLabel as text) is theDefaultLabel then
                set end of defaultItems to (optionLabel as text)
                exit repeat
            end if
        end repeat
    end if

    if (count of defaultItems) is 0 then
        set defaultItems to {item 1 of optionLabels}
    end if

    try
        set chosen to choose from list optionLabels with title theTitle with prompt thePrompt default items defaultItems OK button name "Select" cancel button name "Deny"
    on error errMessage number errNumber
        return "ERROR:" & errNumber & ":" & errMessage
    end try

    if chosen is false then
        return "CANCELLED"
    end if

    set chosenItem to item 1 of chosen
    repeat with optionIndex from 1 to (count of optionLabels)
        if (item optionIndex of optionLabels) as text is (chosenItem as text) then
            -- Return the selected option index (1-based) behind an "OK" status line.
            -- Encoding the index rather than label text means an option label may
            -- contain any characters without being misparsed by the caller.
            return "OK" & linefeed & optionIndex
        end if
    end repeat
    return "CANCELLED"
end run
