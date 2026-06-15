use framework "AppKit"
use scripting additions

on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theDefault to item 3 of argv
    set theIconPath to item 4 of argv
    set theFontSize to (item 5 of argv) as real
    set buttonList to {}
    repeat with i from 6 to (count of argv)
        set end of buttonList to item i of argv
    end repeat

    set alert to current application's NSAlert's alloc()'s init()
    alert's setMessageText:theTitle
    alert's setInformativeText:theMessage
    -- NSAlert anchors the first-added button on the right. Add buttons in reverse
    -- so the on-screen order (left to right) matches buttonList order, and let
    -- NSAlert lay them out natively to avoid overlap and hit-test mismatches.
    repeat with i from (count of buttonList) to 1 by -1
        alert's addButtonWithTitle:((item i of buttonList) as text)
    end repeat
    my setAlertIcon(alert, theIconPath)
    alert's layout()
    my setAlertFontSize(alert, theFontSize)
    my clearButtonDefaultState(alert)
    alert's layout()
    my setAlertWidthForVisibleLines(alert, theMessage, theFontSize)

    set responseCode to (alert's runModal()) as integer
    -- Buttons were added in reverse, so map the return code back to buttonList.
    set addedIndex to responseCode - 999
    if addedIndex < 1 or addedIndex > (count of buttonList) then
        return ""
    end if
    set buttonIndex to (count of buttonList) - addedIndex + 1
    return "button returned:" & (item buttonIndex of buttonList)
end run

on setAlertIcon(alert, theIconPath)
    if theIconPath is "" then
        return
    end if

    set iconImage to current application's NSImage's alloc()'s initWithContentsOfFile:theIconPath
    if iconImage is not missing value then
        alert's setIcon:iconImage
    end if
end setAlertIcon

on setAlertFontSize(alert, theFontSize)
    set contentView to alert's |window|()'s contentView()
    my setSubviewFontSize(contentView, theFontSize)
    repeat with alertButton in (alert's buttons())
        set sourceFont to alertButton's |font|()
        set buttonFont to my resizedFont(sourceFont, theFontSize)
        alertButton's setFont:buttonFont
    end repeat
end setAlertFontSize

on setSubviewFontSize(parentView, theFontSize)
    repeat with childView in (parentView's subviews())
        if ((childView's isKindOfClass:(current application's NSTextField)) as boolean) then
            set sourceFont to childView's |font|()
            set textFont to my resizedFont(sourceFont, theFontSize)
            childView's setFont:textFont
            my setTextFieldAttributedFont(childView, textFont)
        end if
        my setSubviewFontSize(childView, theFontSize)
    end repeat
end setSubviewFontSize

on setTextFieldAttributedFont(textField, textFont)
    set textValue to textField's stringValue()
    set textAttributes to current application's NSDictionary's dictionaryWithObject:textFont forKey:(current application's NSFontAttributeName)
    set attributedText to current application's NSMutableAttributedString's alloc()'s initWithString:textValue attributes:textAttributes
    my setCommandBlockFont(attributedText, textValue, textFont)
    textField's setAttributedStringValue:attributedText
end setTextFieldAttributedFont

on setCommandBlockFont(attributedText, textValue, textFont)
    set textNSString to current application's NSString's stringWithString:textValue
    set commandLabelRange to textNSString's rangeOfString:"Command:"
    if (commandLabelRange's |length| as integer) = 0 then
        return
    end if

    set commandStart to (commandLabelRange's location as integer) + (commandLabelRange's |length| as integer)
    set messageLength to textNSString's |length|()
    set commandStart to my skipCommandLeadingWhitespace(textNSString, commandStart, messageLength)
    if commandStart is greater than or equal to messageLength then
        return
    end if

    set commandEnd to my commandBlockEnd(textNSString, commandStart, messageLength)
    set commandLength to commandEnd - commandStart
    if commandLength is less than or equal to 0 then
        return
    end if

    set codeFont to current application's NSFont's userFixedPitchFontOfSize:(textFont's pointSize())
    if codeFont is missing value then
        set codeFont to textFont
    end if
    set commandRange to current application's NSMakeRange(commandStart, commandLength)
    attributedText's addAttribute:(current application's NSFontAttributeName) value:codeFont range:commandRange
end setCommandBlockFont

on skipCommandLeadingWhitespace(textNSString, commandStart, messageLength)
    repeat while commandStart < messageLength
        set characterRange to current application's NSMakeRange(commandStart, 1)
        set currentCharacter to (textNSString's substringWithRange:characterRange) as text
        if currentCharacter is " " or currentCharacter is linefeed then
            set commandStart to commandStart + 1
        else
            exit repeat
        end if
    end repeat
    return commandStart
end skipCommandLeadingWhitespace

on commandBlockEnd(textNSString, commandStart, messageLength)
    set commandEnd to messageLength
    set searchRange to current application's NSMakeRange(commandStart, messageLength - commandStart)
    repeat with marker in {linefeed & "File:", linefeed & "Description:", linefeed & "URL:", linefeed & "Query:", linefeed & "Prompt:", linefeed & "Pattern:", linefeed & linefeed & quote & "Always Allow" & quote}
        set markerRange to textNSString's rangeOfString:(marker as text) options:0 range:searchRange
        if (markerRange's |length| as integer) > 0 then
            if (markerRange's location as integer) < commandEnd then
                set commandEnd to markerRange's location as integer
            end if
        end if
    end repeat
    return commandEnd
end commandBlockEnd

on setAlertWidthForVisibleLines(alert, textValue, theFontSize)
    set contentView to alert's |window|()'s contentView()
    set textField to my findTextFieldWithValue(contentView, textValue)
    if textField is missing value then
        return
    end if

    set textFont to my resizedFont((textField's |font|()), theFontSize)
    set codeFont to current application's NSFont's userFixedPitchFontOfSize:(textFont's pointSize())
    if codeFont is missing value then
        set codeFont to textFont
    end if
    set longestLineWidth to my longestVisibleLineWidth(textValue, textFont, codeFont)
    if longestLineWidth is less than or equal to 0 then
        return
    end if

    set desiredTextWidth to longestLineWidth + 8
    set maximumTextWidth to my maximumDialogTextWidth()
    if desiredTextWidth is greater than maximumTextWidth then
        set desiredTextWidth to maximumTextWidth
    end if

    set frameSize to item 2 of (textField's frame())
    set currentWidth to (item 1 of frameSize) as real
    if desiredTextWidth is less than or equal to currentWidth then
        return
    end if

    -- Widen the alert through a spacer accessory view so NSAlert re-runs its own
    -- layout pass. Resizing the window directly would break the buttons' layout.
    set spacerView to current application's NSView's alloc()'s initWithFrame:(current application's NSMakeRect(0, 0, desiredTextWidth, 1))
    alert's setAccessoryView:spacerView
    alert's layout()
    my setAlertFontSize(alert, theFontSize)
end setAlertWidthForVisibleLines

on findTextFieldWithValue(parentView, textValue)
    repeat with childView in (parentView's subviews())
        if ((childView's isKindOfClass:(current application's NSTextField)) as boolean) then
            if ((childView's stringValue()) as text) is textValue then
                return childView
            end if
        end if

        set matchingView to my findTextFieldWithValue(childView, textValue)
        if matchingView is not missing value then
            return matchingView
        end if
    end repeat
    return missing value
end findTextFieldWithValue

on longestVisibleLineWidth(textValue, textFont, codeFont)
    set oldDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to linefeed
    set visibleLines to text items of textValue
    set AppleScript's text item delimiters to oldDelimiters

    set longestWidth to 0
    repeat with visibleLine in visibleLines
        set lineWidth to my renderedLineWidth((visibleLine as text), textFont, codeFont)
        if lineWidth is greater than longestWidth then
            set longestWidth to lineWidth
        end if
    end repeat
    return longestWidth
end longestVisibleLineWidth

on renderedLineWidth(lineValue, textFont, codeFont)
    if lineValue is "" then
        return 0
    end if

    set textAttributes to current application's NSDictionary's dictionaryWithObject:textFont forKey:(current application's NSFontAttributeName)
    set codeAttributes to current application's NSDictionary's dictionaryWithObject:codeFont forKey:(current application's NSFontAttributeName)
    set lineNSString to current application's NSString's stringWithString:lineValue
    set lineSize to lineNSString's sizeWithAttributes:textAttributes
    set codeLineSize to lineNSString's sizeWithAttributes:codeAttributes
    set lineWidth to (lineSize's width) as real
    set codeLineWidth to (codeLineSize's width) as real
    if codeLineWidth is greater than lineWidth then
        return codeLineWidth
    end if
    return lineWidth
end renderedLineWidth

on maximumDialogTextWidth()
    set mainScreen to current application's NSScreen's mainScreen()
    if mainScreen is missing value then
        return 1200
    end if

    set visibleFrame to mainScreen's visibleFrame()
    set visibleSize to item 2 of visibleFrame
    set maximumWidth to ((item 1 of visibleSize) as real) - 180
    if maximumWidth is less than 400 then
        return 400
    end if
    return maximumWidth
end maximumDialogTextWidth

on resizedFont(sourceFont, theFontSize)
    if sourceFont is missing value then
        return current application's NSFont's systemFontOfSize:theFontSize
    end if

    set fontManager to current application's NSFontManager's sharedFontManager()
    return fontManager's convertFont:sourceFont toSize:theFontSize
end resizedFont

on clearButtonDefaultState(alert)
    repeat with alertButton in (alert's buttons())
        alertButton's setKeyEquivalent:""
    end repeat
end clearButtonDefaultState
