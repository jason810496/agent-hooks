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
    -- so that once stackAlertButtonsVertically lays them out as a vertical column
    -- (placing the first-added button at the bottom), the visible top-to-bottom
    -- order matches buttonList order.
    repeat with i from (count of buttonList) to 1 by -1
        alert's addButtonWithTitle:((item i of buttonList) as text)
    end repeat
    my setAlertIcon(alert, theIconPath)
    alert's layout()
    my setAlertFontSize(alert, theFontSize)
    my clearButtonDefaultState(alert)
    alert's layout()
    my setAlertWidthForVisibleLines(alert, theMessage, theFontSize)
    my stackAlertButtonsVertically(alert)

    set responseCode to (alert's runModal()) as integer
    -- Buttons were added in reverse, so map the return code back to buttonList.
    set addedIndex to responseCode - 999
    if addedIndex < 1 or addedIndex > (count of buttonList) then
        return ""
    end if
    set buttonIndex to (count of buttonList) - addedIndex + 1
    return "button returned:" & (item buttonIndex of buttonList)
end run

on stackAlertButtonsVertically(alert)
    -- Lay the buttons out as a single vertical column centered in the dialog. NSAlert
    -- packs buttons into a horizontal row by default, which overlaps once the dialog
    -- is widened to fit a long message and the larger dialog font. Stacking top to
    -- bottom removes that failure mode regardless of dialog width or button count.
    -- Keep the raw NSArray for membership tests and coerce a native AppleScript list
    -- for the index/count operations below (reliable across AppleScript-ObjC versions).
    set buttonArray to alert's buttons()
    set buttonViews to buttonArray as list
    set buttonCount to (count of buttonViews)
    if buttonCount is less than 2 then return

    set theWindow to alert's |window|()
    set contentView to theWindow's contentView()
    set contentViewFrame to contentView's frame()
    set contentWidth to (item 1 of item 2 of contentViewFrame) as real
    set contentHeight to (item 2 of item 2 of contentViewFrame) as real

    set gap to 8
    set sideMargin to 20

    -- Measure where the current button band sits and how tall the tallest button is,
    -- in content-view coordinates, before anything is moved.
    set bandBottom to missing value
    set bandTop to missing value
    set buttonHeight to 0
    repeat with theButtonRef in buttonViews
        set theButton to contents of theButtonRef
        theButton's sizeToFit()
        set bandRect to (theButton's superview())'s convertRect:(theButton's frame()) toView:contentView
        set rectBottom to (item 2 of item 1 of bandRect) as real
        set rectHeight to (item 2 of item 2 of bandRect) as real
        set rectTop to rectBottom + rectHeight
        if bandBottom is missing value or rectBottom < bandBottom then set bandBottom to rectBottom
        if bandTop is missing value or rectTop > bandTop then set bandTop to rectTop
        if rectHeight > buttonHeight then set buttonHeight to rectHeight
    end repeat

    set columnHeight to (buttonCount * buttonHeight) + ((buttonCount - 1) * gap)
    set extraHeight to columnHeight - (bandTop - bandBottom)
    if extraHeight is less than 0 then set extraHeight to 0

    -- Reparent the buttons directly onto the content view so they can be positioned
    -- in absolute coordinates, then drop the now-empty native button container.
    set buttonContainer to (item 1 of buttonViews)'s superview()
    if buttonContainer is not missing value and not (buttonContainer's isEqual:contentView) then
        repeat with theButtonRef in buttonViews
            set theButton to contents of theButtonRef
            theButton's removeFromSuperview()
            contentView's addSubview:theButton
        end repeat
        buttonContainer's removeFromSuperview()
    end if

    -- Pin the existing content to the top so growing the window adds room at the
    -- bottom for the taller column rather than stretching the message area. Leave any
    -- near-full-height background or visual-effect view with its own mask so it keeps
    -- resizing to fill the grown window instead of leaving a blank strip at the bottom.
    if extraHeight is greater than 0 then
        repeat with childViewRef in (contentView's subviews())
            set childView to contents of childViewRef
            if ((item 2 of item 2 of (childView's frame())) as real) < (contentHeight - 5) then
                -- Add NSViewMinYMargin (8) so the view stays anchored to the top,
                -- without dropping its other flags (e.g. NSViewWidthSizable).
                set currentMask to (childView's autoresizingMask()) as integer
                if (currentMask div 8) mod 2 is 0 then childView's setAutoresizingMask:(currentMask + 8)
            end if
        end repeat
        set windowFrame to theWindow's frame()
        set grownFrame to current application's NSMakeRect((item 1 of item 1 of windowFrame), ((item 2 of item 1 of windowFrame) - extraHeight), (item 1 of item 2 of windowFrame), ((item 2 of item 2 of windowFrame) + extraHeight))
        theWindow's setFrame:grownFrame display:false
    end if

    -- Find the lowest piece of content (the divider NSAlert draws above the buttons,
    -- or the message text) so the column can be centered in the space between it and
    -- the bottom of the dialog. Gather the content view's own subviews and, when
    -- NSAlert nests the icon/text inside an NSVisualEffectView, that container's
    -- subviews too, so neither a direct accessory view nor the nested content is
    -- missed. Each candidate is measured in content-view coordinates via its own
    -- superview. Skip the action buttons and any near-full-height background/effect
    -- view whose bottom sits at 0, which would otherwise collapse the centering.
    set candidateViews to (contentView's subviews()) as list
    repeat with childViewRef in (contentView's subviews())
        set childView to contents of childViewRef
        if ((childView's isKindOfClass:(current application's NSVisualEffectView)) as boolean) then
            set candidateViews to candidateViews & ((childView's subviews()) as list)
        end if
    end repeat
    set contentFloor to missing value
    repeat with childViewRef in candidateViews
        set childView to contents of childViewRef
        if not ((buttonArray's containsObject:childView) as boolean) then
            set childRect to (childView's superview())'s convertRect:(childView's frame()) toView:contentView
            if ((item 2 of item 2 of childRect) as real) < (contentHeight - 5) then
                set childBottom to (item 2 of item 1 of childRect) as real
                if contentFloor is missing value or childBottom < contentFloor then set contentFloor to childBottom
            end if
        end if
    end repeat
    if contentFloor is missing value then set contentFloor to (bandBottom + columnHeight + gap)

    -- Center the column vertically in that space, and center each button horizontally
    -- on the dialog's mid-line. buttonViews is in reverse on-screen order (added in
    -- reverse), so placing item 1 at the bottom makes the visible top-to-bottom order
    -- match buttonList. Each button keeps its own fitted width so the centering
    -- survives the relayout NSAlert performs while presenting the dialog.
    set regionTop to contentFloor - gap
    set columnBottom to bandBottom
    if (regionTop - bandBottom) > columnHeight then set columnBottom to bandBottom + (((regionTop - bandBottom) - columnHeight) / 2)
    set centerX to contentWidth / 2
    set maxButtonWidth to contentWidth - (sideMargin * 2)
    repeat with buttonIndex from 1 to buttonCount
        set theButton to item buttonIndex of buttonViews
        theButton's sizeToFit()
        set fittedWidth to (item 1 of item 2 of (theButton's frame())) as real
        if fittedWidth > maxButtonWidth then set fittedWidth to maxButtonWidth
        set buttonX to centerX - (fittedWidth / 2)
        if buttonX is less than sideMargin then set buttonX to sideMargin
        set buttonY to columnBottom + ((buttonIndex - 1) * (buttonHeight + gap))
        theButton's setFrame:(current application's NSMakeRect(buttonX, buttonY, fittedWidth, buttonHeight))
        theButton's setAutoresizingMask:0
    end repeat
end stackAlertButtonsVertically

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
    if textValue is missing value then return
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

    set currentWidth to (current application's NSWidth(textField's frame())) as real
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
            set childValue to childView's stringValue()
            if childValue is not missing value and (childValue as text) is textValue then
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
    set maximumWidth to ((current application's NSWidth(visibleFrame)) as real) - 180
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
