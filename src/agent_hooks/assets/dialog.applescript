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
    repeat with buttonTitle in buttonList
        alert's addButtonWithTitle:(buttonTitle as text)
    end repeat
    my setAlertIcon(alert, theIconPath)
    alert's layout()
    my setAlertFontSize(alert, theFontSize)
    my clearButtonDefaultState(alert)
    alert's layout()
    my setAlertWidthForVisibleLines(alert, theMessage, theFontSize)
    my layoutAlertButtons(alert, theMessage)

    set responseCode to (alert's runModal()) as integer
    set buttonIndex to responseCode - 999
    if buttonIndex < 1 or buttonIndex > (count of buttonList) then
        return ""
    end if
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

    set frameRect to textField's frame()
    set frameOrigin to item 1 of frameRect
    set frameSize to item 2 of frameRect
    set currentWidth to (item 1 of frameSize) as real
    if desiredTextWidth is less than or equal to currentWidth then
        return
    end if

    textField's setPreferredMaxLayoutWidth:desiredTextWidth
    textField's setFrame:(current application's NSMakeRect((item 1 of frameOrigin) as real, (item 2 of frameOrigin) as real, desiredTextWidth, (item 2 of frameSize) as real))
    my widenWindowForTextField(alert, textField, desiredTextWidth)
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

on widenWindowForTextField(alert, textField, desiredTextWidth)
    set windowObject to alert's |window|()
    set contentView to windowObject's contentView()
    set contentFrame to contentView's frame()
    set contentSize to item 2 of contentFrame
    set textFrame to textField's frame()
    set textOrigin to item 1 of textFrame
    set requiredContentWidth to ((item 1 of textOrigin) as real) + desiredTextWidth + 24
    set currentContentWidth to (item 1 of contentSize) as real
    if requiredContentWidth is less than or equal to currentContentWidth then
        return
    end if

    windowObject's setContentSize:(current application's NSMakeSize(requiredContentWidth, (item 2 of contentSize) as real))
end widenWindowForTextField

on layoutAlertButtons(alert, theMessage)
    set buttonCount to count of (alert's buttons())
    if buttonCount is 0 then
        return
    end if

    set buttonGap to 8
    set sideMargin to 16
    set bottomMargin to 16
    set totalButtonWidth to (buttonCount - 1) * buttonGap
    set buttonHeight to 28
    repeat with alertButton in (alert's buttons())
        set totalButtonWidth to totalButtonWidth + (my buttonWidthForLayout(alertButton))
        set frameRect to alertButton's frame()
        set frameSize to item 2 of frameRect
        set frameHeight to (item 2 of frameSize) as real
        if frameHeight is greater than buttonHeight then
            set buttonHeight to frameHeight
        end if
    end repeat

    set windowObject to alert's |window|()
    set contentView to windowObject's contentView()
    set layoutBounds to my buttonHorizontalBoundsForLayout(contentView, theMessage, sideMargin)
    set buttonLeftBound to item 1 of layoutBounds
    set buttonRightBound to item 2 of layoutBounds
    set contentFrame to contentView's frame()
    set contentSize to item 2 of contentFrame
    set requiredContentWidth to buttonLeftBound + totalButtonWidth + sideMargin
    if requiredContentWidth is greater than ((item 1 of contentSize) as real) then
        windowObject's setContentSize:(current application's NSMakeSize(requiredContentWidth, (item 2 of contentSize) as real))
        set contentFrame to contentView's frame()
        set contentSize to item 2 of contentFrame
        set layoutBounds to my buttonHorizontalBoundsForLayout(contentView, theMessage, sideMargin)
        set buttonLeftBound to item 1 of layoutBounds
        set buttonRightBound to item 2 of layoutBounds
    end if

    if (buttonRightBound - buttonLeftBound) is less than totalButtonWidth then
        set buttonLeftBound to sideMargin
        set buttonRightBound to ((item 1 of contentSize) as real) - sideMargin
    end if

    -- NSViewMinXMargin + NSViewMaxYMargin: keep buttons anchored after final sizing.
    set buttonAutoresizingMask to 33
    set nextButtonLeftEdge to buttonLeftBound + ((buttonRightBound - buttonLeftBound - totalButtonWidth) / 2)
    repeat with alertButton in (alert's buttons())
        set buttonWidth to my buttonWidthForLayout(alertButton)
        alertButton's setAutoresizingMask:buttonAutoresizingMask
        alertButton's setFrame:(current application's NSMakeRect(nextButtonLeftEdge, bottomMargin, buttonWidth, buttonHeight))
        set nextButtonLeftEdge to nextButtonLeftEdge + buttonWidth + buttonGap
    end repeat
end layoutAlertButtons

on buttonHorizontalBoundsForLayout(contentView, theMessage, sideMargin)
    set contentFrame to contentView's frame()
    set contentSize to item 2 of contentFrame
    set defaultLeftBound to sideMargin
    set defaultRightBound to ((item 1 of contentSize) as real) - sideMargin
    set textField to my findTextFieldWithValue(contentView, theMessage)
    if textField is missing value then
        return {defaultLeftBound, defaultRightBound}
    end if

    set textFrame to textField's frame()
    set textOrigin to item 1 of textFrame
    set textSize to item 2 of textFrame
    set textLeftEdge to (item 1 of textOrigin) as real
    set textRightEdge to textLeftEdge + ((item 1 of textSize) as real)
    if textLeftEdge is less than sideMargin then
        set textLeftEdge to sideMargin
    end if
    if textRightEdge is greater than defaultRightBound then
        set textRightEdge to defaultRightBound
    end if
    if textRightEdge is less than or equal to textLeftEdge then
        return {defaultLeftBound, defaultRightBound}
    end if
    return {textLeftEdge, textRightEdge}
end buttonHorizontalBoundsForLayout

on buttonWidthForLayout(alertButton)
    set buttonSize to alertButton's intrinsicContentSize()
    set buttonWidth to ((buttonSize's width) as real) + 24
    if buttonWidth is less than 80 then
        return 80
    end if
    return buttonWidth
end buttonWidthForLayout

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
