use scripting additions

on run argv
    set theTitle to item 1 of argv
    set thePrompt to item 2 of argv
    set theMultiSelect to (item 3 of argv) is "1"
    set theDefaultLabel to item 4 of argv
    set optionLabels to {}
    repeat with i from 5 to (count of argv)
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
        set chosen to choose from list optionLabels with title theTitle with prompt thePrompt default items defaultItems OK button name "Submit" cancel button name "Cancel" multiple selections allowed theMultiSelect
    on error errMessage number errNumber
        return "ERROR:" & errNumber & ":" & errMessage
    end try

    if chosen is false then
        return "CANCELLED"
    end if

    set output to ""
    repeat with chosenIndex from 1 to (count of chosen)
        if chosenIndex > 1 then
            set output to output & linefeed & "##" & linefeed
        end if
        set output to output & (item chosenIndex of chosen)
    end repeat
    return output
end run
