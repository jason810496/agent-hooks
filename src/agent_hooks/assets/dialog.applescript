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
    my setDefaultButton(alert, theDefault)
    alert's layout()

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
    set attributedText to current application's NSAttributedString's alloc()'s initWithString:textValue attributes:textAttributes
    textField's setAttributedStringValue:attributedText
end setTextFieldAttributedFont

on resizedFont(sourceFont, theFontSize)
    if sourceFont is missing value then
        return current application's NSFont's systemFontOfSize:theFontSize
    end if

    set fontManager to current application's NSFontManager's sharedFontManager()
    return fontManager's convertFont:sourceFont toSize:theFontSize
end resizedFont

on setDefaultButton(alert, theDefault)
    repeat with alertButton in (alert's buttons())
        if ((alertButton's title()) as text) is theDefault then
            alertButton's setKeyEquivalent:(character id 13)
        else
            alertButton's setKeyEquivalent:""
        end if
    end repeat
end setDefaultButton
